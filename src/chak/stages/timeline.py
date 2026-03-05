"""Stage 3: Timeline building — map Whisper segments to canonical lyrics.

Merges build_timelines.py and build_catalog_timelines.py.

CRITICAL FIX: Two-pass matching strategy for music tracks where
Whisper produces unreliable transcriptions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from chak.config import PipelineConfig
from chak.schemas import TimelineEntry, TimelineResult
from chak.utils.io import load_json, write_json, ensure_dir
from chak.utils.similarity import token_overlap
from chak.utils.text import normalize

logger = logging.getLogger(__name__)


def load_alignment(alignment_dir: Path, track_id: str, variant_id: str | None = None) -> dict[str, Any]:
    """Load word-level alignment JSON for a track (or variant)."""
    stem = f"{track_id}_{variant_id}" if variant_id else track_id
    path = alignment_dir / f"{stem}_words.json"
    return load_json(path)


def load_canonical_lines(
    semantic: dict[str, Any],
    track_id: str,
    lyrics_root: Path | None = None,
    variant_id: str | None = None,
    project_root: Path | None = None,
) -> list[str]:
    """Get canonical lyrics from variant file, semantic matrix, or text files.

    Priority:
    1. Variant-specific lyrics: ``shared/semantics/lyrics/{track_id}_{variant_id}.txt``
    2. Text file: ``lyrics/canonical_{track_id}.txt``
    3. Semantic matrix lines
    """
    # Check variant-specific lyrics file first
    if variant_id and project_root:
        lyrics_dir = project_root / "shared" / "semantics" / "lyrics"
        variant_file = lyrics_dir / f"{track_id}_{variant_id}.txt"
        if variant_file.exists():
            with open(variant_file, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            if lines:
                logger.info(
                    "%s/%s: Using variant-specific lyrics (%d lines) from %s",
                    track_id, variant_id, len(lines), variant_file.name,
                )
                return lines

    # Try text file
    if lyrics_root and lyrics_root.is_dir():
        txt_path = lyrics_root / f"canonical_{track_id}.txt"
        if txt_path.exists():
            with open(txt_path, "r", encoding="utf-8") as f:
                return [ln.strip() for ln in f.readlines() if ln.strip()]

    # Fallback: extract from semantic matrix
    track_sem = semantic.get(track_id)
    if not track_sem:
        raise RuntimeError(f"Track {track_id} not found in semantic matrix")

    lines = track_sem.get("lines", [])
    return [line["lyric"] for line in lines]


def _match_segments_to_lines(
    segments: list[dict[str, Any]],
    canonical_lines: list[str],
    min_similarity: float,
) -> list[dict[str, Any]]:
    """Core matching loop: fuzzy-match segments to canonical lyrics.

    Returns a list of timeline entry dicts.
    """
    line_tokens = [normalize(line) for line in canonical_lines]
    occurrence_counts: dict[int, int] = {}
    timeline: list[dict[str, Any]] = []

    current_min_line_index = 0

    for seg in segments:
        seg_text = seg.get("text", "").strip()
        words = seg.get("words", [])
        if not seg_text or not words:
            continue

        seg_tokens = normalize(seg_text)
        best_idx: int | None = None
        best_score = 0.0

        for idx in range(current_min_line_index, len(canonical_lines)):
            score = token_overlap(seg_tokens, line_tokens[idx])
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx is None or best_score < min_similarity:
            # Unmatched → instrumental segment
            start = words[0]["start"]
            end = words[-1]["end"]
            occ = occurrence_counts.get(-1, 0)
            occurrence_counts[-1] = occ + 1
            timeline.append({
                "id": f"instrumental_{occ}",
                "line_index": None,
                "occurrence_index": occ,
                "start": start,
                "end": end,
                "lyric": seg_text,
            })
            continue

        # Matched to canonical line
        start = words[0]["start"]
        end = words[-1]["end"]
        occ = occurrence_counts.get(best_idx, 0)
        occurrence_counts[best_idx] = occ + 1

        timeline.append({
            "id": f"line_{best_idx}_occ_{occ}",
            "line_index": best_idx,
            "occurrence_index": occ,
            "start": start,
            "end": end,
            "lyric": canonical_lines[best_idx],
        })

        # Move forward (never go backwards) — but allow matching same line again
        current_min_line_index = max(current_min_line_index, best_idx)

    return timeline


def _aggregate_and_rematch(
    timeline: list[dict[str, Any]],
    canonical_lines: list[str],
    min_similarity: float,
) -> list[dict[str, Any]]:
    """Pass 2: For consecutive unmatched segments, combine their text
    and try matching the combined text against canonical lines.

    This helps when Whisper splits a lyric line across multiple segments.
    """
    line_tokens = [normalize(line) for line in canonical_lines]
    result: list[dict[str, Any]] = []
    i = 0

    while i < len(timeline):
        entry = timeline[i]

        if entry["line_index"] is not None:
            # Already matched — keep as-is
            result.append(entry)
            i += 1
            continue

        # Collect consecutive unmatched segments
        group = [entry]
        j = i + 1
        while j < len(timeline) and timeline[j]["line_index"] is None:
            group.append(timeline[j])
            j += 1

        if len(group) >= 2:
            # Try combined text
            combined_text = " ".join(e["lyric"] for e in group)
            combined_tokens = normalize(combined_text)

            best_idx: int | None = None
            best_score = 0.0
            for idx, lt in enumerate(line_tokens):
                score = token_overlap(combined_tokens, lt)
                if score > best_score:
                    best_score = score
                    best_idx = idx

            if best_idx is not None and best_score >= min_similarity:
                # Replace the group with a single matched entry
                result.append({
                    "id": f"line_{best_idx}_occ_0",
                    "line_index": best_idx,
                    "occurrence_index": 0,
                    "start": group[0]["start"],
                    "end": group[-1]["end"],
                    "lyric": canonical_lines[best_idx],
                })
                i = j
                continue

        # Could not combine-match: keep all unmatched entries as-is
        result.extend(group)
        i = j

    return result


def build_timeline_for_track(
    alignment_dir: Path,
    album_data_dir: Path,
    semantic: dict[str, Any],
    track_id: str,
    config: PipelineConfig,
    lyrics_root: Path | None = None,
    variant_id: str | None = None,
) -> TimelineResult:
    """Build a canonical line timeline for a single track (or variant).

    Uses two-pass matching for music tracks:
    - Pass 1: Standard fuzzy match
    - Pass 2: Aggregate consecutive unmatched segments and re-match

    When *variant_id* is given, reads variant-qualified alignment and writes
    variant-qualified timeline, but uses bare *track_id* for semantic lookup.
    """
    label = f"{track_id}/{variant_id}" if variant_id else track_id
    logger.info("Building timeline for %s...", label)

    alignment = load_alignment(alignment_dir, track_id, variant_id)
    segments = alignment.get("segments", [])
    # Use variant-specific lyrics if available, else bare track_id semantics
    canonical_lines = load_canonical_lines(
        semantic, track_id, lyrics_root,
        variant_id=variant_id,
        project_root=config.project_root,
    )

    # Determine threshold: lower for music tracks
    is_music_track = track_id in config.timeline.music_tracks
    threshold = (
        config.timeline.music_track_similarity
        if is_music_track
        else config.timeline.min_similarity
    )

    if is_music_track:
        logger.info(
            "%s is a music track — using lower similarity threshold %.2f",
            track_id, threshold,
        )

    # Pass 1: Standard matching
    timeline = _match_segments_to_lines(segments, canonical_lines, threshold)

    # Pass 2: Aggregate consecutive unmatched and re-match
    unmatched_count = sum(1 for e in timeline if e["line_index"] is None)
    if unmatched_count > 0:
        timeline = _aggregate_and_rematch(timeline, canonical_lines, threshold)
        new_unmatched = sum(1 for e in timeline if e["line_index"] is None)
        if new_unmatched < unmatched_count:
            logger.info(
                "Pass 2 recovered %d segments (unmatched: %d -> %d)",
                unmatched_count - new_unmatched, unmatched_count, new_unmatched,
            )

    matched_count = sum(1 for e in timeline if e["line_index"] is not None)
    logger.info(
        "Timeline for %s: %d matched, %d unmatched (of %d segments)",
        label, matched_count, len(timeline) - matched_count, len(segments),
    )

    file_stem = f"{track_id}_{variant_id}" if variant_id else track_id
    out_obj = {"id": file_stem, "timeline": timeline}

    ensure_dir(album_data_dir)
    out_path = album_data_dir / f"{file_stem}.timeline.json"
    write_json(out_path, out_obj)
    logger.info("Wrote timeline -> %s", out_path)

    return TimelineResult.model_validate(out_obj)


def build_album_timelines(
    album_dir: Path,
    config: PipelineConfig,
    *,
    track_id: str | None = None,
    variant_id: str | None = None,
) -> list[TimelineResult]:
    """Build timelines for all (or one) tracks in an album."""
    alignment_dir = album_dir.parent / "alignment"
    lyrics_root = album_dir.parent / "lyrics"
    album_data_dir = album_dir / "data"

    # Auto-derive music_tracks from album_config when not explicitly set
    if not config.timeline.music_tracks:
        from chak.config import derive_music_tracks
        derived = derive_music_tracks(album_dir)
        if derived:
            config.timeline.music_tracks = derived
            logger.info("Auto-derived music tracks: %s", derived)

    if not alignment_dir.exists():
        raise FileNotFoundError(f"Alignment directory not found: {alignment_dir}")

    # Load semantic matrix (base + album-specific merge)
    project_root = config.project_root
    base_semantic_path = project_root / "shared" / "semantics" / "base_semantic_matrix.json"
    semantic: dict[str, Any] = load_json(base_semantic_path)

    album_semantic_path = album_dir / "semantic_matrix.json"
    if album_semantic_path.exists():
        album_semantic = load_json(album_semantic_path)
        semantic.update(album_semantic)
        logger.info("Merged album-specific semantics from %s", album_semantic_path)

    valid_track_ids = set(semantic.keys())
    results: list[TimelineResult] = []

    if track_id:
        if track_id not in valid_track_ids:
            raise ValueError(f"track_id {track_id} not in semantic matrix")
        result = build_timeline_for_track(
            alignment_dir, album_data_dir, semantic, track_id, config, lyrics_root,
            variant_id=variant_id,
        )
        results.append(result)
    else:
        # Find all alignment files that have a matching semantic entry
        alignment_files = sorted(
            f for f in alignment_dir.iterdir()
            if f.suffix == ".json" and f.stem.endswith("_words") and f.stem.startswith("track_")
        )
        track_ids = sorted({f.stem.replace("_words", "") for f in alignment_files})
        filtered_ids = [tid for tid in track_ids if tid in valid_track_ids]

        if not filtered_ids:
            raise RuntimeError("No track_ids from alignment are present in semantic matrix")

        for tid in filtered_ids:
            result = build_timeline_for_track(
                alignment_dir, album_data_dir, semantic, tid, config, lyrics_root,
            )
            results.append(result)

    return results
