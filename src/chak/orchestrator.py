"""Pipeline orchestrator — runs stages as Python function calls.

Replaces studio_pipeline.py + build_album_from_catalog.py.
No more subprocess chaining between Python stages.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from chak.config import PipelineConfig, load_config
from chak.schemas import AlbumConfig
from chak.utils.io import ensure_dir, load_json, write_json

logger = logging.getLogger(__name__)


def load_album_config(config_path: Path) -> AlbumConfig:
    """Load and validate an album_config.json."""
    data = load_json(config_path)
    return AlbumConfig.model_validate(data)


def copy_semantic_assets(project_root: Path, album_dir: Path) -> None:
    """Copy canonical semantic assets into the album folder."""
    shared_semantics = project_root / "shared" / "semantics"

    base_src = shared_semantics / "base_semantic_matrix.json"
    if base_src.exists():
        dst = album_dir / "semantic_matrix.json"
        if not dst.exists():
            shutil.copy2(base_src, dst)
            logger.info("Copied semantic matrix -> %s", dst)

    for filename in ("master_matrix.json", "master_matrix.js"):
        src = shared_semantics / filename
        if src.exists():
            dst = album_dir / filename
            if not dst.exists():
                shutil.copy2(src, dst)
                logger.info("Copied %s -> %s", filename, dst)


def materialize_audio(
    project_root: Path,
    album_dir: Path,
    album_config: AlbumConfig,
) -> list[dict[str, Any]]:
    """Copy MP3 files into album directory with numbered filenames.

    Returns track metadata with audio_file field added.
    """
    repo_root = project_root.parent  # ORANGE_BOX root
    results = []

    for track in sorted(album_config.tracks, key=lambda t: t.slot):
        src_audio = repo_root / track.audio_path
        if not src_audio.exists():
            raise FileNotFoundError(
                f"Audio file not found for slot {track.slot} ({track.track_id}): {src_audio}"
            )

        dest_filename = f"{track.slot:02d} - {track.track_id}.mp3"
        dest_path = album_dir / dest_filename
        shutil.copy2(src_audio, dest_path)
        logger.info("Copied audio slot %d: %s", track.slot, dest_filename)

        results.append({
            **track.model_dump(),
            "audio_file": dest_filename,
        })

    # Write playlist
    playlist_path = album_dir / "00_ALBUM.m3u"
    with open(playlist_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(f"{r['audio_file']}\n")

    # Write album metadata
    meta = {
        "album_id": album_config.album_id,
        "title": album_config.title,
        "artist": album_config.artist,
        "description": album_config.description,
        "source": album_config.source,
        "tracks": results,
    }
    write_json(album_dir / "album_metadata.json", meta)

    return results


def build_album(
    album_id: str,
    config: PipelineConfig,
    *,
    skip_alignment: bool = False,
    skip_media: bool = False,
    reset_failed_media: bool = False,
) -> dict[str, Any]:
    """Build (or rebuild) an album end-to-end.

    Runs all pipeline stages as direct Python function calls.
    Returns a summary dict.
    """
    from chak.stages.align import align_album_tracks
    from chak.stages.export_js import export_album_tracks, generate_albums_index
    from chak.stages.fetch_media import fetch_album_media
    from chak.stages.fuse import fuse_album_tracks
    from chak.stages.manifest import prepare_manifest
    from chak.stages.timeline import build_album_timelines

    project_root = config.project_root
    album_dir = project_root / "albums" / album_id

    if not album_dir.is_dir():
        raise FileNotFoundError(f"Album directory not found: {album_dir}")

    album_config_path = album_dir / "album_config.json"
    if not album_config_path.exists():
        raise FileNotFoundError(f"album_config.json not found in {album_dir}")

    album_config = load_album_config(album_config_path)
    logger.info("Building album '%s' (%s)", album_id, album_config.title)

    ensure_dir(album_dir / "data")
    ensure_dir(album_dir / "media")

    # Copy semantic assets
    copy_semantic_assets(project_root, album_dir)

    # Stage 1: Alignment
    alignment_dir = album_dir.parent / "alignment"
    has_alignment = alignment_dir.is_dir() and any(alignment_dir.glob("track_*_words.json"))

    if not skip_alignment:
        logger.info("── Stage 1: Alignment ──")
        align_album_tracks(album_dir, config)
        has_alignment = True
    else:
        logger.info("── Stage 1: Alignment (skipped) ──")

    # Stage 2: Timelines
    if has_alignment:
        logger.info("── Stage 2: Timeline building ──")
        build_album_timelines(album_dir, config)
    else:
        logger.warning(
            "── Stage 2: Timeline building (skipped — no alignment data) ──\n"
            "  Run 'chak align %s' first, or install Whisper:\n"
            "  pip install openai-whisper whisper-timestamped",
            album_id,
        )

    # Stage 3: Media manifest
    has_timelines = (album_dir / "data").is_dir() and any(
        (album_dir / "data").glob("*.timeline.json")
    )
    manifest = None

    if has_timelines:
        logger.info("── Stage 3: Media manifest ──")
        manifest = prepare_manifest(album_dir, config)

        # Stage 4: Media fetching
        if not skip_media:
            logger.info("── Stage 4: Media fetching ──")
            manifest = fetch_album_media(
                album_dir, config, reset_failed=reset_failed_media,
            )
        else:
            logger.info("── Stage 4: Media fetching (skipped) ──")

        # Stage 5: Fusion
        logger.info("── Stage 5: Fusion ──")
        fused_tracks = fuse_album_tracks(album_dir, config)

        # Stage 6: JS export
        logger.info("── Stage 6: JS export ──")
        export_album_tracks(album_dir, album_id, fused_tracks)
    else:
        logger.warning(
            "── Stages 3-6 skipped — no timeline data ──\n"
            "  Build cannot proceed without alignment + timelines."
        )

    # Regenerate album index
    generate_albums_index(config)

    # Summary
    concepts = manifest.concepts if manifest else {}
    summary = {
        "album_id": album_id,
        "title": album_config.title,
        "tracks": len(album_config.tracks),
        "concepts_total": len(concepts),
        "concepts_ok": sum(1 for c in concepts.values() if c.status == "ok"),
        "concepts_failed": sum(1 for c in concepts.values() if c.status == "failed"),
        "has_alignment": has_alignment,
        "has_timelines": has_timelines,
    }

    logger.info(
        "Build complete: %s — tracks=%d, concepts=%d (ok=%d, failed=%d)",
        summary["album_id"],
        summary["tracks"],
        summary["concepts_total"],
        summary["concepts_ok"],
        summary["concepts_failed"],
    )

    return summary


def build_from_catalog(
    selected_path: Path,
    mapping_path: Path,
    config: PipelineConfig,
) -> str:
    """Create an album from a Choice Kit selection and build it.

    Returns the album_id of the created album.
    """
    from chak.catalog.choicekit import create_album_config_from_selection

    album_id = create_album_config_from_selection(
        selected_path, mapping_path, config.project_root,
    )
    build_album(album_id, config)
    return album_id


def build_all(config: PipelineConfig) -> list[dict[str, Any]]:
    """Rebuild all albums that have an album_config.json."""
    albums_dir = config.project_root / "albums"
    if not albums_dir.is_dir():
        raise FileNotFoundError(f"albums/ directory not found at {albums_dir}")

    summaries = []
    for entry in sorted(albums_dir.iterdir()):
        if not entry.is_dir():
            continue
        if not (entry / "album_config.json").exists():
            continue
        try:
            summaries.append(build_album(entry.name, config))
        except Exception:
            logger.exception("Failed to rebuild album %s", entry.name)

    return summaries
