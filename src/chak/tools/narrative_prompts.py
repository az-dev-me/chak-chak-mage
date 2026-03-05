"""Rewrite semantic matrix prompts with 3-tier narrative hierarchy.

For each canonical line, generates 3 prompts per layer (literal + hidden)
using the master_matrix phase context for narrative coherence:

  Tier 1 (ESTABLISHING): Wide shot anchored to the phase's story arc
  Tier 2 (SCENE):        Medium shot showing the verse/section action
  Tier 3 (MOMENT):       Close-up of the specific lyric's emotion/action

This creates cinematic variety (wide→medium→close) and ensures every image
is connected to the broader narrative, not just isolated line moments.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "mistral-small"
MAX_PROMPT_LEN = 180

# ---------------------------------------------------------------------------
# Phase data from master_matrix.js (parsed at module level)
# ---------------------------------------------------------------------------

PHASES = [
    {
        "id": "phase_1_discovery",
        "theme": "The Arrival — A time traveler lands among cave dwellers with a BIC lighter. The mundane becomes divine.",
        "modern": "First encounter with technology: a teenager discovers the internet, the first iPhone unboxing, Silicon Valley wonder.",
        "literal_arc": "Green phone booth → prehistoric valley → meeting Gralha → the chak-chak moment → instant worship",
        "hidden_arc": "Dusty laptop in attic → first screen glow → tech influencer profile → Apple keynote → product as prayer",
        "tracks": ["track_01", "track_02"],
    },
    {
        "id": "phase_2_the_fire_run",
        "theme": "The Fire Run — Gralha runs with the flame, the tribe cheers, arbitrary rules form.",
        "modern": "The daily hustle: 5:30am alarm → commute → startup grind → burnout → self-help dogma.",
        "literal_arc": "Dawn flame → running with torch → wind in face → flame dies → rules invented → repeat",
        "hidden_arc": "Monday alarm → subway sprint → Slack floods → burnout at desk → self-help gurus → same loop",
        "tracks": ["track_03"],
    },
    {
        "id": "phase_3_the_rules",
        "theme": "The Rules — Tribe fractures into factions. Arguments, holy writ, dogma. The Mage sits detached.",
        "modern": "Political polarization: cable news split screens, echo chambers, Twitter wars, corporate compliance.",
        "literal_arc": "Tribe splits → factions argue → rules ritualized → youth reject → Mage alone on throne → box becomes sacred",
        "hidden_arc": "Family dinner fight → Fox vs MSNBC → compliance training → Gen-Z mocking → CEO in jet → Times Square cathedral",
        "tracks": ["track_04"],
    },
    {
        "id": "phase_4_mudas_spark",
        "theme": "Muda's Spark — The silent observer picks up a stone, strikes it, creates fire without running.",
        "modern": "Free knowledge: library → Linux → Hello World → Wikipedia → open source → fire was always ours.",
        "literal_arc": "Muda watches → picks up stone → tchak tchak → fire! → teaches slowly → even liberation becomes dogma",
        "hidden_arc": "Quiet student → first code → Wikipedia edit → GitHub → repair cafe → open source co-opted",
        "tracks": ["track_05"],
    },
    {
        "id": "phase_5_two_fires",
        "theme": "Two Fires — Gralhistas vs Mudistas. The great schism. Tronco paralyzed. 'I'm just scared of the dark.'",
        "modern": "Culture war: partisan media, cancel culture, tribal chanting, dueling protests, fear as engine.",
        "literal_arc": "Box is law → Muda's wrong → TWO FIRES → GRAL-HA vs MU-DA → Tronco frozen → Where's the Mage?",
        "hidden_arc": "Terms of Service → cancel mob → split-screen news → sports tribal → moderate ignored → CEO gone",
        "tracks": ["track_06"],
    },
    {
        "id": "phase_6_collapse",
        "theme": "The Empty Lighter — Gas runs out, Mage escapes with hedgehog Revolution. Tribe fights over empty shell.",
        "modern": "The crash: CEO exits, e-waste mountains, Black Friday stampede for nothing, logging off.",
        "literal_arc": "Slipped away → threw lighter → tribe fought for empty plastic → ran to green cell → grabbed hedgehog → Revolution",
        "hidden_arc": "Box of belongings → IPO bell → FOMO buying → dead screen → e-waste dump → delete apps → journal by candlelight",
        "tracks": ["track_07"],
    },
    {
        "id": "phase_7_reflection",
        "theme": "The Fire Was Always There — Back on the couch with Revolution. The stone is still on the ground, waiting.",
        "modern": "The mirror: caveman = commuter, campfire = phone screen, tribal chant = brand slogan. THE STONE IS THERE.",
        "literal_arc": "Couch → hedgehog → lighter was just a lighter → stone upon the ground → fire still there → waiting",
        "hidden_arc": "Phone face-down → cave painting = Instagram → morning commute = fire run → wildflower in concrete → waiting",
        "tracks": ["track_08"],
    },
    {
        "id": "phase_8_epilogue",
        "theme": "The Final Message — The lighter was just a lighter. Nothing changed. The fire is still there, waiting.",
        "modern": "Full circle: same apartment, same loop, but the stone is at your feet. Put the phone down. Chak-chak.",
        "literal_arc": "Home → same shit → tool became totem → nothing changed → fire waiting → strike the stone",
        "hidden_arc": "Phone untouched → museum of phones → child strikes rocks on beach → two hands meeting, no phones",
        "tracks": ["track_09"],
    },
]

# Build track→phase lookup
_TRACK_PHASE: dict[str, dict] = {}
for _p in PHASES:
    for _t in _p["tracks"]:
        _TRACK_PHASE[_t] = _p


def get_phase(track_id: str) -> dict:
    return _TRACK_PHASE.get(track_id, PHASES[0])


# ---------------------------------------------------------------------------
# Ollama prompt templates
# ---------------------------------------------------------------------------

LITERAL_SYSTEM = """\
You are a cinematic image prompt writer for SDXL-Turbo.
Rules:
- Write EXACTLY 3 numbered prompts: 1. 2. 3.
- Each prompt is a SHORT scene description for AI image generation (under 140 chars)
- Style: prehistoric, firelit, warm tones, painterly, cinematic
- NO text/words/letters in the image. NO song references.
- Each prompt on its own numbered line."""

LITERAL_USER = """\
STORY ARC: {literal_arc}
THEME: {theme}
LYRIC: {lyric}
MEANING: {meaning}

Write exactly 3 prompts at different scales:
1. WIDE establishing shot of the world: {literal_arc_short}. Prehistoric landscape, cinematic.
2. MEDIUM shot of the current action in this scene. Dramatic, warm tones.
3. CLOSE-UP of the specific emotion/action: "{lyric_short}". Intimate, painterly.

Format: number, period, space, prompt. One per line. Under 140 chars each."""

HIDDEN_SYSTEM = """\
You are a cinematic image prompt writer for SDXL-Turbo.
Rules:
- Write EXACTLY 3 numbered prompts: 1. 2. 3.
- Each prompt is a SHORT scene description for AI image generation (under 140 chars)
- Style: modern, urban, technological, cool tones, photographic, cinematic
- NO text/words/letters in the image. NO song references.
- Each prompt on its own numbered line."""

HIDDEN_USER = """\
MODERN ARC: {hidden_arc}
THEME: {modern}
LYRIC: {lyric}
MEANING: {meaning}

Write exactly 3 prompts at different scales:
1. WIDE establishing shot of the modern world: {hidden_arc_short}. Urban, cinematic.
2. MEDIUM shot of the current modern situation. Contemporary, cool tones.
3. CLOSE-UP of the specific modern emotion/action: "{meaning_short}". Intimate, photographic.

Format: number, period, space, prompt. One per line. Under 140 chars each."""


# ---------------------------------------------------------------------------
# Ollama interaction
# ---------------------------------------------------------------------------

def _call_ollama(system: str, user: str) -> list[str]:
    """Call Ollama, return list of prompt strings."""
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": user,
                "system": system,
                "stream": False,
                "options": {
                    "temperature": 0.75,
                    "num_predict": 512,
                },
            },
            timeout=90,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
    except (requests.RequestException, ValueError) as e:
        logger.warning("Ollama call failed: %s", e)
        return []

    # Parse lines, strip numbering
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    cleaned = []
    for ln in lines:
        # Strip prefixes: "1. ", "1) ", "- ", "* ", "**1.**", etc.
        ln = re.sub(r"^\*{0,2}\d+[\.\)]\*{0,2}\s*", "", ln)
        ln = re.sub(r"^[-*]\s*", "", ln)
        # Strip labels like "ESTABLISHING:", "SCENE:", "MOMENT:"
        ln = re.sub(r"^(ESTABLISHING|SCENE|MOMENT|WIDE|MEDIUM|CLOSE)[:\-–—]\s*", "", ln, flags=re.IGNORECASE)
        ln = ln.strip().strip('"').strip("'")
        if ln and len(ln) > 15:
            cleaned.append(ln[:MAX_PROMPT_LEN])

    return cleaned


def _generate_literal_prompts(
    phase: dict, lyric: str, meaning: str
) -> list[str]:
    """Generate 3 tiered literal-layer prompts."""
    arc_short = phase["literal_arc"].split("→")[0].strip()
    lyric_short = lyric[:80] if len(lyric) > 80 else lyric
    user_msg = LITERAL_USER.format(
        literal_arc=phase["literal_arc"],
        theme=phase["theme"],
        lyric=lyric,
        meaning=meaning,
        literal_arc_short=arc_short,
        lyric_short=lyric_short,
    )
    prompts = _call_ollama(LITERAL_SYSTEM, user_msg)
    if len(prompts) >= 3:
        return prompts[:3]

    # Fallback: deterministic hierarchy
    logger.warning("Ollama literal returned %d prompts, using fallback", len(prompts))
    return _literal_fallback(phase, lyric, meaning)


def _generate_hidden_prompts(
    phase: dict, lyric: str, meaning: str
) -> list[str]:
    """Generate 3 tiered hidden-layer prompts."""
    arc_short = phase["hidden_arc"].split("→")[0].strip()
    meaning_short = meaning[:80] if len(meaning) > 80 else meaning
    user_msg = HIDDEN_USER.format(
        hidden_arc=phase["hidden_arc"],
        modern=phase["modern"],
        lyric=lyric,
        meaning=meaning,
        hidden_arc_short=arc_short,
        meaning_short=meaning_short,
    )
    prompts = _call_ollama(HIDDEN_SYSTEM, user_msg)
    if len(prompts) >= 3:
        return prompts[:3]

    logger.warning("Ollama hidden returned %d prompts, using fallback", len(prompts))
    return _hidden_fallback(phase, lyric, meaning)


def _literal_fallback(phase: dict, lyric: str, meaning: str) -> list[str]:
    """Deterministic fallback for literal prompts."""
    arc_parts = phase["literal_arc"].split("→")
    world = arc_parts[0].strip() if arc_parts else "prehistoric valley"
    lyric_words = " ".join(lyric.split()[:8])
    meaning_words = " ".join(meaning.split()[:6])

    return [
        f"wide cinematic shot of {world}, prehistoric landscape, firelit, dramatic lighting, painterly"[:MAX_PROMPT_LEN],
        f"medium shot of {lyric_words}, warm tones, cave setting, cinematic"[:MAX_PROMPT_LEN],
        f"close-up emotional {meaning_words}, firelight on face, intimate portrait, painterly"[:MAX_PROMPT_LEN],
    ]


def _hidden_fallback(phase: dict, lyric: str, meaning: str) -> list[str]:
    """Deterministic fallback for hidden prompts."""
    arc_parts = phase["hidden_arc"].split("→")
    world = arc_parts[0].strip() if arc_parts else "modern city"
    meaning_words = " ".join(meaning.split()[:8])

    return [
        f"wide shot of {world}, modern urban setting, cool tones, photographic, cinematic"[:MAX_PROMPT_LEN],
        f"medium shot of {meaning_words}, contemporary scene, blue light, cinematic"[:MAX_PROMPT_LEN],
        f"close-up detail of {meaning_words}, emotional, modern, intimate photography"[:MAX_PROMPT_LEN],
    ]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_narrative_prompts(
    matrix_path: Path,
    *,
    dry_run: bool = False,
    delay: float = 0.3,
    backup: bool = True,
) -> dict[str, int]:
    """Rewrite all prompts in the semantic matrix with 3-tier narrative hierarchy.

    Returns stats dict: {track_id: lines_rewritten}.
    """
    with open(matrix_path, encoding="utf-8") as f:
        matrix = json.load(f)

    if backup and not dry_run:
        backup_path = matrix_path.with_suffix(".json.bak")
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(matrix, f, indent=2, ensure_ascii=False)
        logger.info("Backed up matrix -> %s", backup_path)

    stats: dict[str, int] = {}
    total = 0

    for track_id in sorted(matrix.keys()):
        track_data = matrix[track_id]
        lines = track_data.get("lines", [])
        phase = get_phase(track_id)
        count = 0

        logger.info(
            "=== %s (%d lines) — Phase: %s ===",
            track_id, len(lines), phase["id"],
        )

        for li, line in enumerate(lines):
            lyric = line.get("lyric", "")
            meaning = line.get("real_meaning", "")
            if not lyric:
                continue

            if dry_run:
                literal = [f"[DRY T1] {phase['id']}", f"[DRY T2] scene", f"[DRY T3] {lyric[:40]}"]
                hidden = [f"[DRY T1] {phase['id']} hidden", f"[DRY T2] scene", f"[DRY T3] {meaning[:40]}"]
            else:
                literal = _generate_literal_prompts(phase, lyric, meaning)
                time.sleep(delay)
                hidden = _generate_hidden_prompts(phase, lyric, meaning)
                time.sleep(delay)

            line["media_queries"] = literal
            line["hidden_media_queries"] = hidden
            count += 1
            total += 1

            if total % 10 == 0:
                logger.info("  ... %d lines rewritten so far", total)

        stats[track_id] = count

    if not dry_run:
        with open(matrix_path, "w", encoding="utf-8") as f:
            json.dump(matrix, f, indent=2, ensure_ascii=False)
        logger.info("Wrote narrative matrix -> %s", matrix_path)

    logger.info(
        "Narrative prompt generation complete: %d lines across %d tracks",
        total, len(stats),
    )
    return stats
