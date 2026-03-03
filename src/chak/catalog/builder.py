"""Build album configurations from Choice Kit classification data.

Selects the best variant per track based on classification score and
file size, avoiding tiny clips and TTS artifacts when better options exist.
"""

from __future__ import annotations

import logging
import os
import shutil
from collections import defaultdict
from pathlib import Path

from chak.schemas import AlbumConfig
from chak.utils.io import ensure_dir, load_json, write_json

logger = logging.getLogger(__name__)

# Minimum file size in bytes to consider a variant "full-length"
# (avoids selecting tiny clips / stubs)
_MIN_SIZE_BYTES = 500_000  # 500 KB


def _load_classification(choicekit_dir: Path) -> list[dict]:
    """Load the classification report from the Choice Kit."""
    report_path = choicekit_dir / "classification_report.json"
    if not report_path.exists():
        raise FileNotFoundError(
            f"classification_report.json not found in {choicekit_dir}"
        )
    data = load_json(report_path)
    if isinstance(data, dict):
        return data.get("assigned", [])
    return data


def _track_dir_name(track_id: str, track_names: dict[str, str]) -> str:
    """Map track_id -> Choice Kit subdirectory name.

    E.g. track_01 + names={track_01: "Prologue_The_Green_Booth"}
         -> "TRACK_01_Prologue_The_Green_Booth"
    """
    name = track_names.get(track_id, "")
    num = track_id.replace("track_", "")
    if name:
        return f"TRACK_{num}_{name}"
    return f"TRACK_{num}"


def select_best_variants(
    choicekit_dir: Path,
    track_names: dict[str, str],
    *,
    min_size: int = _MIN_SIZE_BYTES,
) -> dict[str, dict]:
    """Pick the best variant per track from classification_report.json.

    Selection criteria (in order):
    1. Among non-TTS variants with file size >= min_size, pick highest score
    2. If all variants are TTS (e.g. spoken-word tracks), pick largest TTS file
    3. If no variant meets size threshold, pick the largest file

    Returns dict mapping track_id -> {raw_id, score, reason, size, audio_path}.
    """
    entries = _load_classification(choicekit_dir)

    # Group by best_track
    by_track: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        track_id = entry.get("best_track")
        if track_id:
            by_track[track_id].append(entry)

    selections: dict[str, dict] = {}

    for track_id in sorted(by_track.keys()):
        variants = by_track[track_id]
        dir_name = _track_dir_name(track_id, track_names)
        track_dir = choicekit_dir / dir_name

        # Augment each variant with file size
        for v in variants:
            raw_id = v["raw_id"]
            mp3_path = track_dir / f"{raw_id}.mp3"
            v["_size"] = mp3_path.stat().st_size if mp3_path.exists() else 0
            v["_abs_path"] = str(mp3_path)
            v["_rel_path"] = str(mp3_path.relative_to(choicekit_dir.parent))

        # Separate TTS and non-TTS
        non_tts = [v for v in variants if v.get("reason") != "tts"]
        tts_only = [v for v in variants if v.get("reason") == "tts"]

        # Try non-TTS variants first, with size filter
        big_enough = [v for v in non_tts if v["_size"] >= min_size]

        if big_enough:
            # Best score among large-enough non-TTS variants
            best = max(big_enough, key=lambda v: (v["best_score"], v["_size"]))
        elif non_tts:
            # All non-TTS variants are small — pick largest
            best = max(non_tts, key=lambda v: v["_size"])
        elif tts_only:
            # All variants are TTS — pick the largest (best quality TTS)
            best = max(tts_only, key=lambda v: v["_size"])
        else:
            logger.warning("No variants found for %s", track_id)
            continue

        selections[track_id] = {
            "raw_id": best["raw_id"],
            "score": best["best_score"],
            "reason": best.get("reason", ""),
            "size": best["_size"],
            "abs_path": best["_abs_path"],
            "rel_path": best["_rel_path"],
        }

        logger.info(
            "%s: selected %s (score=%.3f, %s, %.1f MB)",
            track_id, best["raw_id"][:12], best["best_score"],
            best.get("reason", ""), best["_size"] / 1024 / 1024,
        )

    return selections


def build_album_from_classification(
    choicekit_dir: Path,
    album_id: str,
    title: str,
    project_root: Path,
    track_names: dict[str, str],
    track_titles: dict[str, str],
    *,
    artist: str = "Chak Chak Mage",
    description: str = "",
    copy_audio: bool = True,
) -> AlbumConfig:
    """Build a complete album from classification report.

    1. Selects best variant per track
    2. Writes album_config.json
    3. Optionally copies MP3 files to album directory

    Returns the validated AlbumConfig.
    """
    selections = select_best_variants(choicekit_dir, track_names)

    if not selections:
        raise ValueError("No variants selected — classification_report.json may be empty")

    album_dir = project_root / "albums" / album_id
    ensure_dir(album_dir)

    tracks = []
    for i, track_id in enumerate(sorted(selections.keys()), 1):
        sel = selections[track_id]
        raw_id = sel["raw_id"]
        src_path = Path(sel["abs_path"])

        # Destination filename: "NN - track_NN.mp3"
        dest_name = f"{i:02d} - {track_id}.mp3"
        dest_path = album_dir / dest_name

        if copy_audio and src_path.exists():
            if not dest_path.exists() or dest_path.stat().st_size != src_path.stat().st_size:
                shutil.copy2(src_path, dest_path)
                logger.info("Copied %s -> %s", src_path.name, dest_name)
            else:
                logger.info("Already present: %s", dest_name)

        # audio_path in config is relative to the Choice Kit parent
        audio_rel = sel["rel_path"]

        tracks.append({
            "slot": i,
            "track_id": track_id,
            "variant_id": f"Track_{i:02d}_Best",
            "audio_path": audio_rel,
        })

    config_dict = {
        "album_id": album_id,
        "title": title,
        "artist": artist,
        "description": description or f"Album built from {choicekit_dir.name} (best variant per track).",
        "source": choicekit_dir.name,
        "tracks": tracks,
    }

    # Validate
    album_config = AlbumConfig.model_validate(config_dict)

    # Write
    config_path = album_dir / "album_config.json"
    write_json(config_path, config_dict)
    logger.info("Wrote %s with %d tracks", config_path, len(tracks))

    return album_config
