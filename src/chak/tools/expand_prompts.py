"""Expand media_queries in the semantic matrix using Ollama.

For each canonical line, generates 2 additional image prompts to create
a visual micro-narrative per line:
  1. (existing) Establishing shot — wide/context
  2. (new) Detail/action — close-up or key moment
  3. (new) Emotion/meaning — abstract or emotional interpretation

Uses a local Ollama instance (localhost:11434) with mistral-small.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "mistral-small"
MAX_PROMPT_LEN = 180

SYSTEM_PROMPT = """\
You are a cinematic image prompt writer for an AI image generator (SDXL-Turbo).
You write SHORT, vivid image descriptions (under 150 characters each).
Style: cinematic lighting, warm tones, painterly, evocative.
Never include text, words, or letters in the image.
Never reference the song, album, or music.
Output ONLY the two prompts, one per line. No numbering, no labels, no explanation."""

USER_TEMPLATE = """\
Given this scene for a music visual:

ESTABLISHING SHOT: {existing_prompt}
LYRIC: {lyric}
MEANING: {meaning}

Write 2 additional image prompts that continue this visual narrative:
1. A DETAIL or ACTION shot — zoom into a key element or show movement
2. An EMOTION or ABSTRACT shot — capture the feeling or deeper meaning

Each prompt must be under 150 characters. Output only the two prompts, one per line."""


def _call_ollama(existing_prompt: str, lyric: str, meaning: str) -> list[str]:
    """Call Ollama to generate 2 additional prompts."""
    user_msg = USER_TEMPLATE.format(
        existing_prompt=existing_prompt,
        lyric=lyric,
        meaning=meaning,
    )

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": user_msg,
                "system": SYSTEM_PROMPT,
                "stream": False,
                "options": {
                    "temperature": 0.8,
                    "num_predict": 256,
                },
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
    except (requests.RequestException, ValueError) as e:
        logger.warning("Ollama call failed: %s", e)
        return _fallback_prompts(existing_prompt, lyric, meaning)

    # Parse: expect 2 lines
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Strip numbering like "1. " or "1) " or "- "
    cleaned = []
    for ln in lines:
        for prefix in ("1.", "2.", "1)", "2)", "-", "*"):
            if ln.startswith(prefix):
                ln = ln[len(prefix):].strip()
                break
        if ln and len(ln) > 10:
            cleaned.append(ln[:MAX_PROMPT_LEN])

    if len(cleaned) >= 2:
        return cleaned[:2]

    # Not enough valid lines — use fallback
    logger.warning("Ollama returned %d valid prompts, using fallback", len(cleaned))
    return _fallback_prompts(existing_prompt, lyric, meaning)


def _fallback_prompts(existing_prompt: str, lyric: str, meaning: str) -> list[str]:
    """Generate deterministic fallback prompts when Ollama is unavailable."""
    # Extract key words from lyric and meaning
    lyric_words = lyric.split()[:6]
    meaning_words = meaning.split()[:6]

    detail = f"close-up detail of {' '.join(lyric_words)}, cinematic macro, warm lighting, painterly"
    emotion = f"abstract emotional {' '.join(meaning_words)}, ethereal atmosphere, golden hour, dreamlike"

    return [detail[:MAX_PROMPT_LEN], emotion[:MAX_PROMPT_LEN]]


def expand_semantic_prompts(
    matrix_path: Path,
    *,
    dry_run: bool = False,
    delay: float = 0.3,
) -> dict[str, int]:
    """Expand media_queries in the semantic matrix from 1 to 3 per line.

    Returns stats dict: {track_id: lines_expanded}.
    """
    with open(matrix_path, encoding="utf-8") as f:
        matrix = json.load(f)

    stats: dict[str, int] = {}
    total_expanded = 0

    for track_id in sorted(matrix.keys()):
        track_data = matrix[track_id]
        lines = track_data.get("lines", [])
        expanded_count = 0

        for li, line in enumerate(lines):
            queries = line.get("media_queries", [])

            # Skip if already has 3+ prompts
            if len(queries) >= 3:
                continue

            existing = queries[0] if queries else ""
            lyric = line.get("lyric", "")
            meaning = line.get("real_meaning", "")

            if not existing:
                logger.warning("%s line %d: no existing prompt, skipping", track_id, li)
                continue

            if dry_run:
                new_prompts = ["[DRY RUN detail prompt]", "[DRY RUN emotion prompt]"]
            else:
                new_prompts = _call_ollama(existing, lyric, meaning)
                time.sleep(delay)

            # Keep existing prompt first, add new ones
            line["media_queries"] = [existing] + new_prompts
            expanded_count += 1
            total_expanded += 1

            if total_expanded % 10 == 0:
                logger.info("Expanded %d lines so far...", total_expanded)

        stats[track_id] = expanded_count

    if not dry_run:
        with open(matrix_path, "w", encoding="utf-8") as f:
            json.dump(matrix, f, indent=2, ensure_ascii=False)
        logger.info("Wrote expanded matrix -> %s", matrix_path)

    logger.info(
        "Prompt expansion complete: %d lines expanded across %d tracks",
        total_expanded, len(stats),
    )
    return stats
