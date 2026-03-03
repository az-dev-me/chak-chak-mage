"""Validate catalog_mapping.json integrity.

Ported from pipeline/validate_catalog_mapping.py.
"""

from __future__ import annotations

import logging
from pathlib import Path

from chak.utils.io import load_json

logger = logging.getLogger(__name__)


def validate_catalog_mapping(
    mapping_path: Path,
    repo_root: Path,
) -> bool:
    """Validate catalog_mapping.json entries.

    Checks:
    - All tracks have track_id, variant_id, audio_path
    - No placeholder values
    - All audio_path files exist
    """
    mapping = load_json(mapping_path)
    tracks = mapping.get("tracks", [])

    if not tracks:
        logger.error("No tracks found in %s", mapping_path)
        return False

    all_ok = True
    for track in tracks:
        track_id = track.get("track_id", "")
        variant_id = track.get("variant_id", "")
        audio_path = track.get("audio_path", "")

        if not track_id or not variant_id or not audio_path:
            logger.error("Missing fields in track entry: %s", track)
            all_ok = False
            continue

        if "REPLACE_ME" in audio_path:
            logger.error("Placeholder audio_path for %s/%s", track_id, variant_id)
            all_ok = False
            continue

        full_path = repo_root / audio_path
        if not full_path.exists():
            logger.error("Audio file not found for %s/%s: %s", track_id, variant_id, full_path)
            all_ok = False
        else:
            logger.info("OK: %s / %s", track_id, variant_id)

    return all_ok
