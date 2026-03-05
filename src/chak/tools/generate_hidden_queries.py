"""Generate hidden_media_queries in the semantic matrix using Ollama.

For each canonical line, generates 3 image prompts based on the real_meaning
field to create a modern/urban visual narrative (the "hidden" parallel):
  1. A modern-world establishing shot
  2. A detail/close-up of the modern parallel
  3. An emotional/abstract interpretation

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
Style: modern, urban, contemporary photography, gritty realism, cinematic.
The images depict the HIDDEN MODERN MEANING behind an ancient allegory.
Focus on: smartphones, social media, consumerism, corporate life, technology,
urban landscapes, crowds, screens, algorithms, hustle culture.
Never include text, words, or letters in the image.
Output ONLY the three prompts, one per line. No numbering, no labels."""

USER_TEMPLATE = """\
An ancient story uses this allegory:

LYRIC: {lyric}
HIDDEN MODERN MEANING: {real_meaning}

Write 3 image prompts showing the MODERN REALITY behind this allegory:
1. An ESTABLISHING shot of the modern parallel — wide/environmental
2. A DETAIL or CLOSE-UP — zoom into a key modern element
3. An EMOTION or ABSTRACT shot — capture the modern feeling

Each prompt under 150 characters. Output only the three prompts, one per line."""


def _call_ollama(lyric: str, real_meaning: str) -> list[str]:
    """Call Ollama to generate 3 hidden-narrative prompts."""
    user_msg = USER_TEMPLATE.format(lyric=lyric, real_meaning=real_meaning)

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
                    "num_predict": 384,
                },
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
    except (requests.RequestException, ValueError) as e:
        logger.warning("Ollama call failed: %s", e)
        return _fallback_prompts(lyric, real_meaning)

    # Parse: expect 3 lines
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    cleaned = []
    for ln in lines:
        for prefix in ("1.", "2.", "3.", "1)", "2)", "3)", "-", "*"):
            if ln.startswith(prefix):
                ln = ln[len(prefix) :].strip()
                break
        if ln and len(ln) > 10:
            cleaned.append(ln[:MAX_PROMPT_LEN])

    if len(cleaned) >= 3:
        return cleaned[:3]

    # Not enough valid lines — pad with fallback
    logger.warning("Ollama returned %d valid prompts, padding with fallback", len(cleaned))
    fallback = _fallback_prompts(lyric, real_meaning)
    while len(cleaned) < 3:
        cleaned.append(fallback[len(cleaned) % len(fallback)])
    return cleaned[:3]


def _fallback_prompts(lyric: str, real_meaning: str) -> list[str]:
    """Generate deterministic fallback prompts when Ollama is unavailable."""
    meaning_words = real_meaning.split()[:8]
    lyric_words = lyric.split()[:6]

    establishing = f"modern city scene, {' '.join(meaning_words[:4])}, neon lights, cinematic urban photography"
    detail = f"close-up of smartphone screen showing {' '.join(lyric_words[:4])}, blue glow, contemporary"
    emotion = f"abstract modern interpretation of {' '.join(meaning_words[:5])}, urban atmosphere, moody"

    return [
        establishing[:MAX_PROMPT_LEN],
        detail[:MAX_PROMPT_LEN],
        emotion[:MAX_PROMPT_LEN],
    ]


def generate_hidden_queries(
    matrix_path: Path,
    *,
    dry_run: bool = False,
    delay: float = 0.3,
) -> dict[str, int]:
    """Generate hidden_media_queries in the semantic matrix from real_meaning.

    Returns stats dict: {track_id: lines_generated}.
    """
    with open(matrix_path, encoding="utf-8") as f:
        matrix = json.load(f)

    stats: dict[str, int] = {}
    total_generated = 0

    for track_id in sorted(matrix.keys()):
        track_data = matrix[track_id]
        lines = track_data.get("lines", [])
        generated_count = 0

        for li, line in enumerate(lines):
            existing = line.get("hidden_media_queries", [])

            # Skip if already has 3+ hidden prompts
            if len(existing) >= 3:
                continue

            real_meaning = line.get("real_meaning", "")
            lyric = line.get("lyric", "")

            if not real_meaning:
                logger.warning("%s line %d: no real_meaning, skipping", track_id, li)
                continue

            if dry_run:
                new_prompts = [
                    "[DRY RUN hidden establishing]",
                    "[DRY RUN hidden detail]",
                    "[DRY RUN hidden emotion]",
                ]
            else:
                new_prompts = _call_ollama(lyric, real_meaning)
                time.sleep(delay)

            line["hidden_media_queries"] = new_prompts
            generated_count += 1
            total_generated += 1

            if total_generated % 10 == 0:
                logger.info("Generated hidden queries for %d lines so far...", total_generated)

        stats[track_id] = generated_count

    if not dry_run:
        with open(matrix_path, "w", encoding="utf-8") as f:
            json.dump(matrix, f, indent=2, ensure_ascii=False)
        logger.info("Wrote hidden queries -> %s", matrix_path)

    logger.info(
        "Hidden query generation complete: %d lines across %d tracks",
        total_generated,
        len(stats),
    )
    return stats
