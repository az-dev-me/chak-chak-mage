"""Stage 5: Media fetching — download images for album concepts.

Provider chain (in order):
1. Local GPU (diffusers + Stable Diffusion on local CUDA GPU)
2. Stable Horde (stablehorde.net) — free, no key needed, AI-generated
3. Pollinations (image.pollinations.ai / gen.pollinations.ai) — free or keyed
4. SVG placeholder — always works, lets pipeline complete

Key features:
- Local GPU generation with diffusers (SD 2.1, float16)
- Stable Horde async generation with polling
- Exponential backoff on retries
- Content-Type validation (reject HTML error pages saved as .jpg)
- --reset-failed support
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests

from chak.config import MediaConfig, PipelineConfig
from chak.schemas import MediaManifest
from chak.utils.io import ensure_dir, load_json, write_json

logger = logging.getLogger(__name__)

# ── Local GPU generation (diffusers) ──────────────────


_local_pipeline = None  # singleton — loaded once, reused


def _get_local_pipeline(config: MediaConfig):
    """Lazily load the Stable Diffusion pipeline on the configured GPU.

    Uses a module-level singleton so the model is only loaded once per process.
    """
    global _local_pipeline
    if _local_pipeline is not None:
        return _local_pipeline

    try:
        import torch

        device = config.gpu_device
        model_id = config.model_id
        logger.info("Loading model '%s' on %s (float16)...", model_id, device)

        # Use the specific pipeline class to avoid import chain issues
        # with AutoPipelineForText2Image (transformers v5 compat)
        if "sdxl" in model_id.lower() or "xl" in model_id.lower():
            from diffusers import StableDiffusionXLPipeline
            pipe = StableDiffusionXLPipeline.from_pretrained(
                model_id, torch_dtype=torch.float16, variant="fp16",
            )
        else:
            from diffusers import StableDiffusionPipeline
            pipe = StableDiffusionPipeline.from_pretrained(
                model_id, torch_dtype=torch.float16,
                safety_checker=None, requires_safety_checker=False,
            )

        pipe = pipe.to(device)
        pipe.set_progress_bar_config(disable=True)

        # Memory optimizations
        if hasattr(pipe, "enable_attention_slicing"):
            pipe.enable_attention_slicing()

        _local_pipeline = pipe
        logger.info("Pipeline ready on %s", device)
        return pipe

    except Exception as exc:
        logger.error("Failed to load local GPU pipeline: %s", exc)
        return None


def _fetch_local_gpu(
    query: str,
    filepath: Path,
    config: MediaConfig,
) -> bool:
    """Generate an image locally using Stable Diffusion on GPU."""
    import torch

    pipe = _get_local_pipeline(config)
    if pipe is None:
        return False

    prompt = query.strip()
    if len(prompt) > config.max_prompt_length:
        prompt = prompt[: config.max_prompt_length - 3] + "..."

    # Deterministic seed from prompt for reproducibility
    seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16)
    generator = torch.Generator(device=config.gpu_device).manual_seed(seed)

    enhanced_prompt = (
        f"{prompt}. cinematic film still, dramatic lighting, "
        "rich colors, detailed, 8k, professional photography"
    )
    prompt_preview = prompt[:40]

    # Dimensions must be multiples of 8 for diffusers
    width = (config.image_width // 8) * 8
    height = (config.image_height // 8) * 8

    logger.info("Local GPU: generating '%s...' (%dx%d)", prompt_preview, width, height)

    try:
        result = pipe(
            prompt=enhanced_prompt,
            negative_prompt=(
                "blurry, low quality, distorted, deformed, text, watermark, "
                "abstract, noisy, artifacts, oversaturated, monochrome, ugly"
            ),
            width=width,
            height=height,
            num_inference_steps=config.num_inference_steps,
            guidance_scale=config.guidance_scale,
            generator=generator,
        )

        image = result.images[0]

        ensure_dir(filepath.parent)
        out_path = filepath.with_suffix(".jpg")
        image.save(out_path, "JPEG", quality=90)

        file_size = out_path.stat().st_size
        logger.info("Generated %s (%d bytes) via local GPU", out_path.name, file_size)
        return True

    except torch.cuda.OutOfMemoryError:
        logger.error(
            "CUDA out of memory on %s. Try reducing image dimensions or "
            "freeing GPU memory.", config.gpu_device,
        )
        return False
    except Exception as exc:
        logger.error("Local GPU generation failed: %s", exc)
        return False


# ── Stable Horde (primary — free, no key needed) ───────


_HORDE_API = "https://stablehorde.net/api/v2"
_HORDE_ANON_KEY = "0000000000"  # anonymous access
_HORDE_POLL_INTERVAL = 8  # seconds between status checks
_HORDE_MAX_WAIT = 120  # max seconds to wait for generation


def _fetch_stable_horde(
    query: str,
    filepath: Path,
    config: MediaConfig,
) -> bool:
    """Generate an image via Stable Horde (free, async)."""
    prompt = query.strip()
    if len(prompt) > config.max_prompt_length:
        prompt = prompt[: config.max_prompt_length - 3] + "..."

    prompt_preview = prompt[:40]

    # Stable Horde anonymous limit varies by demand (as low as 640x640).
    # Keep dimensions conservatively under that limit.
    width = min(config.image_width, 640)
    height = min(config.image_height, 448)
    # Stable Diffusion needs multiples of 64
    width = (width // 64) * 64
    height = (height // 64) * 64

    payload = {
        "prompt": f"{prompt}, high quality, cinematic lighting, digital art",
        "params": {
            "width": width,
            "height": height,
            "steps": 20,
            "n": 1,
            "sampler_name": "k_euler",
            "cfg_scale": 7.0,
        },
        "nsfw": False,
        "censor_nsfw": True,
        "trusted_workers": False,
        "slow_workers": True,
    }

    headers = {"apikey": _HORDE_ANON_KEY, "Content-Type": "application/json"}

    # Step 1: Submit async job
    try:
        resp = requests.post(
            f"{_HORDE_API}/generate/async",
            json=payload,
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 202:
            logger.warning(
                "Stable Horde submit failed: HTTP %d — %s",
                resp.status_code, resp.text[:200],
            )
            return False

        job_id = resp.json().get("id")
        if not job_id:
            return False

        logger.info("Stable Horde: job %s for '%s...'", job_id[:12], prompt_preview)

    except requests.RequestException as exc:
        logger.debug("Stable Horde submit error: %s", exc)
        return False

    # Step 2: Poll for completion
    elapsed = 0
    while elapsed < _HORDE_MAX_WAIT:
        time.sleep(_HORDE_POLL_INTERVAL)
        elapsed += _HORDE_POLL_INTERVAL

        try:
            check = requests.get(
                f"{_HORDE_API}/generate/check/{job_id}", timeout=10,
            )
            check_data = check.json()

            if check_data.get("faulted"):
                logger.warning("Stable Horde job faulted for '%s...'", prompt_preview)
                return False

            if check_data.get("done"):
                break
        except requests.RequestException:
            continue
    else:
        logger.warning(
            "Stable Horde timed out (%ds) for '%s...'", _HORDE_MAX_WAIT, prompt_preview,
        )
        return False

    # Step 3: Retrieve result
    try:
        result = requests.get(
            f"{_HORDE_API}/generate/status/{job_id}", timeout=15,
        )
        generations = result.json().get("generations", [])
        if not generations:
            return False

        img_url = generations[0].get("img")
        if not img_url:
            return False

        # Download the image
        img_resp = requests.get(img_url, timeout=30)
        content_type = img_resp.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            logger.debug("Stable Horde returned non-image: %s", content_type)
            return False

        if len(img_resp.content) < 1000:
            return False

        ensure_dir(filepath.parent)
        # Determine extension from content type
        ext = ".webp" if "webp" in content_type else ".jpg"
        out_path = filepath.with_suffix(ext)
        with open(out_path, "wb") as f:
            f.write(img_resp.content)

        logger.info("Downloaded %s (%d bytes) via Stable Horde", out_path.name, len(img_resp.content))
        return True

    except requests.RequestException as exc:
        logger.debug("Stable Horde download error: %s", exc)
        return False


# ── Pollinations (fallback) ─────────────────────────────


_POLLINATIONS_ENDPOINTS = [
    "https://gen.pollinations.ai/image/{prompt}?width={width}&height={height}&seed={seed}",
    "https://image.pollinations.ai/prompt/{prompt}?model=flux&width={width}&height={height}&nologo=true&enhance=true",
]


def _resolve_api_key(config: MediaConfig) -> str:
    """Get API key from config or environment variable."""
    key = config.api_key
    if not key:
        key = os.environ.get("POLLINATIONS_API_KEY", "")
    return key.strip()


def _try_endpoint(
    url: str,
    headers: dict[str, str],
    timeout: int,
    prompt_preview: str,
) -> bytes | None:
    """Attempt a single GET request and validate the response is an image."""
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)

        if resp.status_code in (401, 403, 530):
            logger.debug(
                "Endpoint returned HTTP %d: %s", resp.status_code, url[:80],
            )
            return None

        if resp.status_code != 200:
            logger.debug(
                "Endpoint returned HTTP %d for '%s...': %s",
                resp.status_code, prompt_preview, url[:80],
            )
            return None

        content_type = resp.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            logger.debug("Non-image Content-Type '%s' from %s", content_type, url[:80])
            return None

        if len(resp.content) < 1000:
            logger.debug("Tiny response (%d bytes) from %s", len(resp.content), url[:80])
            return None

        return resp.content

    except requests.Timeout:
        logger.debug("Timeout (%ds) for %s", timeout, url[:80])
        return None
    except requests.RequestException as exc:
        logger.debug("Request failed for %s: %s", url[:80], exc)
        return None


def _fetch_pollinations(
    query: str,
    filepath: Path,
    config: MediaConfig,
) -> bool:
    """Fetch an image from Pollinations AI, trying multiple endpoints."""
    prompt = query.strip()
    if len(prompt) > config.max_prompt_length:
        prompt = prompt[: config.max_prompt_length - 3] + "..."

    encoded = quote_plus(prompt)
    seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16) % 100000
    prompt_preview = prompt[:40]

    api_key = _resolve_api_key(config)

    headers = {
        "User-Agent": "ChakChakMage/1.0",
        "Accept": "image/*,*/*;q=0.8",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    for endpoint_tpl in _POLLINATIONS_ENDPOINTS:
        if "gen.pollinations.ai" in endpoint_tpl and not api_key:
            continue

        url = endpoint_tpl.format(
            prompt=encoded,
            width=config.image_width,
            height=config.image_height,
            seed=seed,
        )

        logger.info("Pollinations: trying '%s...'", prompt_preview)
        data = _try_endpoint(url, headers, config.timeout, prompt_preview)

        if data:
            ensure_dir(filepath.parent)
            with open(filepath, "wb") as f:
                f.write(data)
            logger.info("Downloaded %s (%d bytes) via Pollinations", filepath.name, len(data))
            return True

    return False


# ── SVG placeholder (last resort) ──────────────────────


def _generate_placeholder(
    query: str,
    filepath: Path,
    config: MediaConfig,
) -> bool:
    """Generate a minimal SVG placeholder image."""
    prompt_preview = query.strip()[:60]
    hue = int(hashlib.md5(query.encode()).hexdigest()[:4], 16) % 360

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{config.image_width}" height="{config.image_height}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:hsl({hue},40%,15%)"/>
      <stop offset="100%" style="stop-color:hsl({(hue + 60) % 360},30%,8%)"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <text x="50%" y="48%" text-anchor="middle" fill="hsl({hue},50%,60%)"
        font-family="sans-serif" font-size="18" opacity="0.7">{prompt_preview}</text>
  <text x="50%" y="56%" text-anchor="middle" fill="#555"
        font-family="sans-serif" font-size="12">[placeholder — run chak media-fetch --reset-failed]</text>
</svg>"""

    ensure_dir(filepath.parent)
    svg_path = filepath.with_suffix(".svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)

    logger.info("Generated placeholder %s", svg_path.name)
    return True


# ── Provider chain ──────────────────────────────────────


def _fetch_image(
    query: str,
    filepath: Path,
    config: MediaConfig,
) -> bool:
    """Try to fetch an image using the configured provider chain.

    Order depends on config.provider:
    - local_gpu: GPU → placeholder
    - stable_horde/auto: stable_horde → pollinations → placeholder
    - pollinations: pollinations → fallback
    """
    provider = config.provider

    if provider == "local_gpu":
        if _fetch_local_gpu(query, filepath, config):
            return True
        # Fall back to placeholder if GPU fails
        if config.fallback_provider == "stable_horde":
            return _fetch_stable_horde(query, filepath, config)
        return _generate_placeholder(query, filepath, config)

    elif provider in ("stable_horde", "auto"):
        if _fetch_stable_horde(query, filepath, config):
            return True
        if _fetch_pollinations(query, filepath, config):
            return True
        return _generate_placeholder(query, filepath, config)

    elif provider == "pollinations":
        if _fetch_pollinations(query, filepath, config):
            return True
        if config.fallback_provider == "stable_horde":
            return _fetch_stable_horde(query, filepath, config)
        if config.fallback_provider == "placeholder":
            return _generate_placeholder(query, filepath, config)
        return False

    elif provider == "local":
        return filepath.exists()

    elif provider == "placeholder":
        return _generate_placeholder(query, filepath, config)

    else:
        logger.warning("Unknown provider '%s', using auto", provider)
        if _fetch_stable_horde(query, filepath, config):
            return True
        return _generate_placeholder(query, filepath, config)


# ── Public API ──────────────────────────────────────────


def fetch_album_media(
    album_dir: Path,
    config: PipelineConfig,
    *,
    reset_failed: bool = False,
    reset_placeholders: bool = False,
    max_requests: int | None = None,
    seed_dir: Path | None = None,
) -> MediaManifest:
    """Fetch images for all pending concepts in media_manifest.json.

    Parameters
    ----------
    album_dir:
        Path to the album directory.
    config:
        Pipeline configuration.
    reset_failed:
        If True, reset all "failed" concepts to "pending" before fetching.
    reset_placeholders:
        If True, reset SVG placeholder concepts to "pending" and delete
        the SVG files so real images can be fetched.
    max_requests:
        Maximum number of network requests to make. None = unlimited.
    seed_dir:
        Optional directory with pre-existing images to seed from.
    """
    manifest_path = album_dir / "media_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"media_manifest.json not found at {manifest_path}. "
            "Run media manifest preparation first."
        )

    manifest_data = load_json(manifest_path)
    concepts = manifest_data.get("concepts", {})
    if not concepts:
        logger.info("No concepts found in media_manifest.json")
        return MediaManifest()

    media_dir = album_dir / "media"
    ensure_dir(media_dir)

    # Reset SVG placeholders if requested
    if reset_placeholders:
        reset_count = 0
        for query, meta in concepts.items():
            fname = meta.get("filename", "")
            if fname.endswith(".svg"):
                svg_path = media_dir / fname
                if svg_path.exists():
                    svg_path.unlink()
                meta["status"] = "pending"
                meta["filename"] = fname.rsplit(".", 1)[0] + ".jpg"
                reset_count += 1
        if reset_count:
            logger.info("Reset %d SVG placeholders to pending", reset_count)

    media_cfg = config.media
    requests_made = 0

    logger.info(
        "Media fetch: provider=%s, %d concepts, reset_failed=%s",
        media_cfg.provider, len(concepts), reset_failed,
    )

    for query, meta in concepts.items():
        status = meta.get("status", "pending")
        filename = meta.get("filename")
        if not filename:
            continue

        filepath = media_dir / filename

        # If file already exists on disk (any image format), mark as ok
        for suffix in ("", ".webp", ".svg"):
            check_path = filepath.with_suffix(suffix) if suffix else filepath
            if check_path.exists() and check_path.stat().st_size > 100:
                if status != "ok":
                    meta["status"] = "ok"
                    if suffix:
                        meta["filename"] = check_path.name
                break
        else:
            # No existing file found — continue to fetch logic below
            pass

        if meta.get("status") == "ok":
            continue

        # Try seeding from cache
        if seed_dir and seed_dir.is_dir():
            seed_path = seed_dir / filename
            if seed_path.exists():
                logger.info("Seeding '%s...' from %s", query[:30], seed_path)
                ensure_dir(filepath.parent)
                shutil.copy2(seed_path, filepath)
                meta["status"] = "ok"
                continue

        # Handle failed concepts
        if status == "failed":
            if reset_failed:
                logger.info("Resetting failed concept: '%s...'", query[:30])
                meta["status"] = "pending"
                status = "pending"
            else:
                continue

        if status != "pending":
            continue

        # Respect request cap
        if max_requests is not None and requests_made >= max_requests:
            logger.info("Reached max requests (%d), stopping", max_requests)
            break

        # Fetch with exponential backoff retries
        success = False
        for attempt in range(media_cfg.max_retries):
            if attempt > 0:
                backoff = min(2**attempt, 16)
                logger.info("Retry %d/%d (backoff %ds)...", attempt + 1, media_cfg.max_retries, backoff)
                time.sleep(backoff)

            if media_cfg.request_delay > 0 and attempt == 0:
                time.sleep(media_cfg.request_delay)

            if _fetch_image(query, filepath, media_cfg):
                success = True
                requests_made += 1
                break

        if success:
            # Update filename if output format differs (webp, svg)
            for suffix in (".webp", ".svg"):
                alt = filepath.with_suffix(suffix)
                if alt.exists() and not filepath.exists():
                    meta["filename"] = alt.name
                    break
            meta["status"] = "ok"
        else:
            meta["status"] = "failed"
            logger.warning(
                "Failed to fetch image for '%s...' after %d attempts",
                query[:40], media_cfg.max_retries,
            )

    # Save updated manifest
    write_json(manifest_path, {"concepts": concepts})

    ok_count = sum(1 for m in concepts.values() if m.get("status") == "ok")
    failed_count = sum(1 for m in concepts.values() if m.get("status") == "failed")
    pending_count = sum(1 for m in concepts.values() if m.get("status") == "pending")

    logger.info(
        "Media fetch complete: %d ok, %d failed, %d pending (of %d total)",
        ok_count, failed_count, pending_count, len(concepts),
    )

    return MediaManifest.model_validate({"concepts": concepts})
