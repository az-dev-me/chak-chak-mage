"""Convert a Choice Kit selection into an album_config.json.

Ported from pipeline/choicekit_to_album_config.py.
Key fix: returns the album_id directly (no more mtime-based guessing).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from chak.schemas import AlbumConfig
from chak.utils.io import ensure_dir, load_json, write_json

logger = logging.getLogger(__name__)


def build_album_config_from_selection(
    selected_path: Path,
    mapping_path: Path,
) -> dict[str, Any]:
    """Build an album_config dict from selected_album.json + catalog_mapping.json."""
    selected = load_json(selected_path)
    mapping = load_json(mapping_path)

    album_id = selected.get("album_id")
    title = selected.get("title")
    artist = selected.get("artist")
    description = selected.get("description", "")
    source = selected.get("source", "THE_CHAK_CHAK_MAGE_CHOICE_KIT")

    if not album_id or not title or not artist:
        raise ValueError("selected_album.json must include 'album_id', 'title', and 'artist'.")

    mapping_tracks = mapping.get("tracks", [])
    if not mapping_tracks:
        raise ValueError("catalog_mapping.json has no 'tracks' entries.")

    by_variant = {t["variant_id"]: t for t in mapping_tracks if "variant_id" in t}

    out_tracks = []
    for track in selected.get("tracks", []):
        slot = track.get("slot")
        variant_id = track.get("variant_id")
        if slot is None or not variant_id:
            raise ValueError(f"Malformed selected track entry: {track}")

        mapping_entry = by_variant.get(variant_id)
        if not mapping_entry:
            raise ValueError(f"variant_id '{variant_id}' not found in catalog_mapping.json")

        track_id = mapping_entry.get("track_id")
        audio_path = mapping_entry.get("audio_path")
        if not track_id or not audio_path:
            raise ValueError(f"Mapping entry missing track_id/audio_path for variant {variant_id}")

        out_tracks.append({
            "slot": slot,
            "track_id": track_id,
            "variant_id": variant_id,
            "audio_path": audio_path,
        })

    out_tracks.sort(key=lambda t: int(t["slot"]))

    return {
        "album_id": album_id,
        "title": title,
        "artist": artist,
        "description": description,
        "source": source,
        "tracks": out_tracks,
    }


def create_album_config_from_selection(
    selected_path: Path,
    mapping_path: Path,
    project_root: Path,
) -> str:
    """Create album_config.json from selection and return the album_id.

    This fixes the old approach that guessed the album_id by scanning
    filesystem mtimes.
    """
    config_dict = build_album_config_from_selection(selected_path, mapping_path)

    # Validate with Pydantic
    album_config = AlbumConfig.model_validate(config_dict)
    album_id = album_config.album_id

    album_dir = project_root / "albums" / album_id
    ensure_dir(album_dir)

    out_path = album_dir / "album_config.json"
    write_json(out_path, config_dict)
    logger.info("Wrote album_config.json for %s -> %s", album_id, out_path)

    return album_id
