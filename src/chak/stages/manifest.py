"""Stage 4: Media manifest preparation.

Aggregates all media_queries from the semantic matrix and track_visuals
into a single media_manifest.json with stable filenames and status tracking.

BUG FIX: Auto-generates intro/outro queries when track_visuals.json is empty.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from chak.config import PipelineConfig
from chak.schemas import MediaManifest, MediaConcept
from chak.utils.io import load_json, write_json, ensure_dir

logger = logging.getLogger(__name__)


def _gather_queries_from_semantic(semantic: dict[str, Any]) -> list[str]:
    """Extract all media_queries from the semantic matrix."""
    queries: list[str] = []
    for track_id in sorted(semantic.keys()):
        track = semantic[track_id]
        for line in track.get("lines", []):
            for q in line.get("media_queries", []):
                if q and q.strip():
                    queries.append(q.strip())
    return queries


def _gather_queries_from_visuals(track_visuals: dict[str, Any]) -> list[str]:
    """Extract intro/outro queries from track_visuals.json."""
    queries: list[str] = []
    for track_id in sorted(track_visuals.keys()):
        entry = track_visuals[track_id]
        for q in entry.get("intro_queries", []):
            if q and q.strip():
                queries.append(q.strip())
        for q in entry.get("outro_queries", []):
            if q and q.strip():
                queries.append(q.strip())
    return queries


def _auto_generate_visuals(semantic: dict[str, Any]) -> list[str]:
    """When track_visuals.json has no queries, auto-generate from
    the first and last semantic lines of each track."""
    queries: list[str] = []
    for track_id in sorted(semantic.keys()):
        track = semantic[track_id]
        lines = track.get("lines", [])
        if not lines:
            continue

        # Use first line's media queries as intro
        first = lines[0]
        for q in first.get("media_queries", [])[:1]:
            if q and q.strip():
                queries.append(q.strip())

        # Use last line's media queries as outro
        if len(lines) > 1:
            last = lines[-1]
            for q in last.get("media_queries", [])[:1]:
                if q and q.strip():
                    queries.append(q.strip())

    return queries


def prepare_manifest(
    album_dir: Path,
    config: PipelineConfig,
) -> MediaManifest:
    """Create or update media_manifest.json for an album.

    Gathers all unique media queries and assigns stable filenames.
    Preserves status of existing concepts (allows incremental builds).
    """
    project_root = config.project_root

    # Load semantic matrix (base + album-specific merge)
    base_semantic_path = project_root / "shared" / "semantics" / "base_semantic_matrix.json"
    semantic: dict[str, Any] = load_json(base_semantic_path)

    album_semantic_path = album_dir / "semantic_matrix.json"
    if album_semantic_path.exists():
        album_semantic = load_json(album_semantic_path)
        semantic.update(album_semantic)

    # Gather all queries
    all_queries: list[str] = []
    all_queries.extend(_gather_queries_from_semantic(semantic))

    # Load track visuals
    visuals_path = project_root / "track_visuals.json"
    visual_queries: list[str] = []
    if visuals_path.exists():
        track_visuals = load_json(visuals_path)
        visual_queries = _gather_queries_from_visuals(track_visuals)

    if not visual_queries:
        # BUG FIX: Auto-generate when track_visuals.json is empty
        logger.info("track_visuals.json has no queries — auto-generating from semantic matrix")
        visual_queries = _auto_generate_visuals(semantic)

    all_queries.extend(visual_queries)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_queries: list[str] = []
    for q in all_queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)

    logger.info("Gathered %d unique media concepts", len(unique_queries))

    # Load existing manifest to preserve status
    manifest_path = album_dir / "media_manifest.json"
    existing_concepts: dict[str, dict[str, Any]] = {}
    if manifest_path.exists():
        try:
            existing = load_json(manifest_path)
            existing_concepts = existing.get("concepts", {})
        except (ValueError, KeyError):
            pass

    # Build new manifest preserving "ok" status, resetting "failed" to "pending"
    concepts: dict[str, MediaConcept] = {}
    for idx, query in enumerate(unique_queries):
        filename = f"c{idx:04d}.jpg"

        if query in existing_concepts:
            old = existing_concepts[query]
            old_status = old.get("status", "pending")
            old_filename = old.get("filename", filename)

            if old_status == "ok":
                concepts[query] = MediaConcept(filename=old_filename, status="ok")
            else:
                # Reset failed/pending to pending for retry
                concepts[query] = MediaConcept(filename=old_filename, status="pending")
        else:
            concepts[query] = MediaConcept(filename=filename, status="pending")

    manifest = MediaManifest(concepts=concepts)

    ensure_dir(album_dir)
    write_json(manifest_path, manifest.model_dump())
    logger.info(
        "Wrote media_manifest.json: %d concepts (%d ok, %d pending)",
        len(concepts),
        sum(1 for c in concepts.values() if c.status == "ok"),
        sum(1 for c in concepts.values() if c.status == "pending"),
    )

    return manifest
