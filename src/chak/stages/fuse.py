"""Stage 6: Fusion — merge timeline + semantics + alignment + manifest.

Lyrics-driven fusion: ALL canonical lines from the semantic matrix appear
in the player output. Missing Whisper matches get interpolated timing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from chak.config import PipelineConfig
from chak.schemas import (
    FusedTimelineEntry,
    FusedTrackData,
    MediaEntry,
    WordTiming,
)
from chak.utils.io import load_json
from chak.utils.similarity import token_overlap
from chak.utils.text import normalize

logger = logging.getLogger(__name__)


# ── Data loading helpers ────────────────────────────────


def load_semantic_matrix(project_root: Path, album_dir: Path) -> dict[str, Any]:
    """Load and merge base + album-specific semantic matrix."""
    base_path = project_root / "shared" / "semantics" / "base_semantic_matrix.json"
    semantic = load_json(base_path)

    album_path = album_dir / "semantic_matrix.json"
    if album_path.exists():
        album_semantic = load_json(album_path)
        semantic.update(album_semantic)

    return semantic


def load_semantic_overrides(project_root: Path) -> dict[str, Any]:
    """Load per-line semantic overrides."""
    path = project_root / "semantic_overrides.json"
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except (ValueError, FileNotFoundError):
        return {}



def load_manifest(album_dir: Path) -> dict[str, Any] | None:
    """Load media_manifest.json if it exists."""
    path = album_dir / "media_manifest.json"
    if not path.exists():
        return None
    try:
        return load_json(path)
    except (ValueError, FileNotFoundError):
        return None


def load_timeline(album_dir: Path, track_id: str) -> dict[str, Any]:
    """Load timeline JSON for a track."""
    path = album_dir / "data" / f"{track_id}.timeline.json"
    return load_json(path)


# ── Semantic index (cross-track fuzzy lookup) ───────────


def build_semantic_index(semantic_matrix: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten all semantic lines into an index for cross-track matching."""
    index: list[dict[str, Any]] = []
    for track_id in sorted(semantic_matrix.keys()):
        track = semantic_matrix[track_id]
        for idx, line in enumerate(track.get("lines", [])):
            lyric = line.get("lyric", "")
            index.append({
                "track_id": track_id,
                "line_index": idx,
                "lyric": lyric,
                "tokens": normalize(lyric),
                "semantic_line": line,
            })
    return index


def best_semantic_for_lyric(
    semantic_index: list[dict[str, Any]],
    lyric: str,
    min_sim: float = 0.45,
) -> dict[str, Any] | None:
    """Find the best semantic match for a lyric across all tracks."""
    if not semantic_index:
        return None
    seg_tokens = normalize(lyric)
    if not seg_tokens:
        return None

    best: dict[str, Any] | None = None
    best_score = 0.0

    for entry in semantic_index:
        score = token_overlap(seg_tokens, entry["tokens"])
        if score > best_score:
            best_score = score
            best = entry

    if not best or best_score < min_sim:
        return None
    return best


# ── Alignment loading ──────────────────────────────────


def load_alignment_for_track(
    album_dir: Path,
    track_id: str,
) -> dict[str, Any] | None:
    """Load word-level Whisper alignment for a track, if available."""
    alignment_dir = album_dir.parent / "alignment"
    path = alignment_dir / f"{track_id}_words.json"
    if not path.exists():
        return None
    try:
        return load_json(path)
    except (ValueError, FileNotFoundError):
        return None


def flatten_words(alignment: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract all word-level entries from alignment segments.

    Returns a flat list of {start, end, text} dicts sorted by start time.
    """
    words: list[dict[str, Any]] = []
    for seg in alignment.get("segments", []):
        for w in seg.get("words", []):
            words.append({
                "start": w["start"],
                "end": w["end"],
                "text": w.get("text", w.get("word", "")),
            })
    words.sort(key=lambda w: w["start"])
    return words


def words_for_range(
    all_words: list[dict[str, Any]],
    start: float,
    end: float,
) -> list[dict[str, Any]]:
    """Get Whisper words that fall within a time range.

    Uses strict boundaries (no tolerance) to avoid picking up
    words from adjacent segments — e.g. an instrumental ♪ note
    ending at 29.50s should NOT be included in a line starting at 29.50s.
    """
    return [w for w in all_words if w["start"] >= start - 0.05 and w["end"] <= end + 0.05]


def synthesize_words_from_lyric(
    lyric: str,
    start: float,
    end: float,
) -> list[WordTiming]:
    """Fallback: evenly distribute canonical words across the time range.

    Used when no Whisper alignment data is available for a segment.
    """
    if not lyric or not lyric.strip():
        return []
    words = lyric.split()
    if not words:
        return []
    duration = max(0.0, end - start)
    per_word = duration / len(words) if len(words) > 0 else 0.0
    return [
        WordTiming(
            start=round(start + per_word * i, 3),
            end=round(start + per_word * (i + 1), 3),
            text=w,
        )
        for i, w in enumerate(words)
    ]


def align_words_to_lyric(
    lyric: str,
    whisper_words: list[dict[str, Any]],
    start: float,
    end: float,
) -> list[WordTiming]:
    """Map canonical lyric text onto Whisper word timings.

    Uses Whisper's actual rhythm (start/end per word) but displays
    canonical text. When word counts differ, redistributes timing
    proportionally across canonical words.

    Falls back to synthesize_words_from_lyric if no Whisper words.
    """
    if not lyric or not lyric.strip():
        return []
    canonical_words = lyric.split()
    if not canonical_words:
        return []
    if not whisper_words:
        return synthesize_words_from_lyric(lyric, start, end)

    n_canon = len(canonical_words)
    n_whisper = len(whisper_words)

    if n_canon == n_whisper:
        # Perfect 1:1 mapping — use Whisper timing directly
        return [
            WordTiming(
                start=round(whisper_words[i]["start"], 3),
                end=round(whisper_words[i]["end"], 3),
                text=canonical_words[i],
            )
            for i in range(n_canon)
        ]

    # Word counts differ — redistribute Whisper timing proportionally.
    # Use the total Whisper time span, divide it by canonical word count
    # but preserve the overall rhythm shape.
    w_start = whisper_words[0]["start"]
    w_end = whisper_words[-1]["end"]
    total_duration = max(w_end - w_start, 0.01)

    # Build cumulative time boundaries from Whisper words
    # then interpolate positions for canonical word boundaries
    result: list[WordTiming] = []
    for i in range(n_canon):
        # Map canonical word index to proportional position in Whisper time
        frac_start = i / n_canon
        frac_end = (i + 1) / n_canon
        ws = round(w_start + frac_start * total_duration, 3)
        we = round(w_start + frac_end * total_duration, 3)
        result.append(WordTiming(start=ws, end=we, text=canonical_words[i]))

    return result


# ── Media array construction ────────────────────────────


def build_media_array(
    media_queries: list[str],
    start: float,
    end: float,
    manifest: dict[str, Any] | None,
    beats: list[float] | None = None,
) -> list[MediaEntry]:
    """Build media entries for a timeline segment.

    When beat timestamps are provided, image transitions are synced
    to musical beats. Otherwise, distributes evenly across duration.
    The number of images used is min(available prompts, beats + 1).
    """
    if not media_queries:
        return []

    # Beat-aware: determine how many images and their offsets
    from chak.utils.beats import beats_in_range
    line_beats = beats_in_range(beats, start, end) if beats else []

    if line_beats:
        # Use beats to determine image count and offsets
        n_images = min(len(media_queries), len(line_beats) + 1)
        selected_queries = media_queries[:n_images]
        offsets = [0.0] + [round(b - start, 2) for b in line_beats[:n_images - 1]]
    else:
        # Fallback: even distribution
        selected_queries = media_queries
        n_images = len(selected_queries)
        duration = max(0.0, end - start)
        step = duration / n_images if n_images > 1 else 0.0
        offsets = [round(step * i, 2) for i in range(n_images)]

    concepts = manifest.get("concepts", {}) if manifest else None

    entries: list[MediaEntry] = []

    for idx, query in enumerate(selected_queries):
        offset = offsets[idx] if idx < len(offsets) else 0.0

        if concepts:
            meta = concepts.get(query)

            # If exact query has no ok image, find closest available concept
            if not meta or meta.get("status") != "ok" or not meta.get("filename"):
                best_fallback = _find_closest_concept(query, concepts)
                if best_fallback:
                    meta = best_fallback["meta"]
                    query = best_fallback["query"]
                else:
                    # No available image at all — skip this entry
                    continue

            entries.append(MediaEntry(
                offset=offset,
                url=f"media/{meta['filename']}",
                query=query,
            ))
        else:
            # No manifest — use placeholder URL
            entries.append(MediaEntry(
                offset=offset,
                url=f"media/placeholder_{idx:04d}.jpg",
                query=query,
            ))

    return entries


def _find_closest_concept(
    query: str,
    concepts: dict[str, Any],
) -> dict[str, Any] | None:
    """Find the closest 'ok' concept by token similarity."""
    seg_tokens = normalize(query)
    if not seg_tokens:
        return None

    best: dict[str, Any] | None = None
    best_score = 0.0

    for other_query, other_meta in concepts.items():
        if not other_meta or other_meta.get("status") != "ok" or not other_meta.get("filename"):
            continue
        other_tokens = normalize(other_query)
        score = token_overlap(seg_tokens, other_tokens)
        if score > best_score:
            best_score = score
            best = {"query": other_query, "meta": other_meta}

    return best if best and best_score > 0 else None


# ── Timing interpolation ───────────────────────────────


def _interpolate_timing(
    line_index: int,
    num_lines: int,
    matched_timing: dict[int, list[dict[str, Any]]],
) -> tuple[float, float]:
    """Interpolate timing for a canonical line with no Whisper match.

    Divides the gap between the nearest matched neighbors evenly
    among all consecutive unmatched lines in that gap.
    """
    # Find nearest matched line BEFORE this one
    prev_end = 0.0
    for j in range(line_index - 1, -1, -1):
        if j in matched_timing:
            prev_end = matched_timing[j][0]["end"]
            break

    # Find nearest matched line AFTER this one
    next_start = None
    for j in range(line_index + 1, num_lines):
        if j in matched_timing:
            next_start = matched_timing[j][0]["start"]
            break

    if next_start is not None and next_start > prev_end:
        # Find the contiguous gap of unmatched lines containing this one
        gap_first = line_index
        while gap_first > 0 and (gap_first - 1) not in matched_timing:
            gap_first -= 1
        gap_last = line_index
        while gap_last < num_lines - 1 and (gap_last + 1) not in matched_timing:
            gap_last += 1

        total_in_gap = gap_last - gap_first + 1
        position = line_index - gap_first
        per_line = (next_start - prev_end) / total_in_gap
        start = round(prev_end + per_line * position, 2)
        end = round(start + per_line, 2)
    elif next_start is None:
        # No matched line after — estimate 2s per line
        start = round(prev_end + 0.5, 2)
        end = round(start + 2.0, 2)
        prev_end = end  # chain subsequent missing lines
    else:
        # next_start <= prev_end (shouldn't happen)
        start = round(prev_end + 0.1, 2)
        end = round(start + 1.0, 2)

    return start, end


# ── Track object assembly ───────────────────────────────


def build_track_object(
    album_dir: Path,
    album_id: str,
    semantic_matrix: dict[str, Any],
    semantic_index: list[dict[str, Any]],
    track_id: str,
    semantic_overrides: dict[str, Any],
    manifest: dict[str, Any] | None,
    config: PipelineConfig,
) -> FusedTrackData:
    """Build a complete fused track object for the player.

    LYRICS-DRIVEN: iterates over ALL canonical lines from the semantic
    matrix, guaranteeing every lyric appears in the player output.
    Lines without Whisper matches get interpolated timing.
    """
    sem_track = semantic_matrix.get(track_id)
    if not sem_track:
        raise ValueError(f"No semantic data found for {track_id}")

    base_timeline_data = load_timeline(album_dir, track_id)
    base_timeline = base_timeline_data.get("timeline", [])
    lines = sem_track.get("lines", [])

    # ── Step 0: Load Whisper word-level alignment (if available) ──
    alignment = load_alignment_for_track(album_dir, track_id)
    all_words = flatten_words(alignment) if alignment else []
    if all_words:
        logger.info(
            "%s: loaded %d Whisper words for karaoke timing",
            track_id, len(all_words),
        )

    # ── Step 0b: Load beat data (if available) ──
    from chak.utils.beats import load_beats
    track_beats = load_beats(track_id, album_dir)
    if track_beats:
        logger.info(
            "%s: loaded %d beat timestamps for media sync",
            track_id, len(track_beats),
        )

    # ── Step 1: Index timeline entries by canonical line_index ──
    matched_timing: dict[int, list[dict[str, Any]]] = {}
    instrumental_entries: list[dict[str, Any]] = []

    for entry in base_timeline:
        li = entry.get("line_index")
        if li is not None and 0 <= li < len(lines):
            matched_timing.setdefault(li, []).append({
                "start": entry["start"],
                "end": entry["end"],
                "id": entry["id"],
                "occ": entry.get("occurrence_index", 0),
            })
        else:
            instrumental_entries.append(entry)

    # Merge consecutive segments that matched the same canonical line.
    # Whisper may split a long spoken sentence into multiple segments
    # (e.g., TTS tracks). If the gap between them is < 2s, merge into
    # one entry spanning the full range. Preserves genuine repetitions
    # (like choruses) where the gap is much larger.
    for li in matched_timing:
        occs = sorted(matched_timing[li], key=lambda o: o["start"])
        if len(occs) <= 1:
            continue
        merged: list[dict[str, Any]] = [occs[0]]
        for occ in occs[1:]:
            prev = merged[-1]
            gap = occ["start"] - prev["end"]
            if gap < 2.0:
                # Merge: extend previous entry to cover this one
                prev["end"] = max(prev["end"], occ["end"])
            else:
                # Genuine repetition — keep separate
                merged.append(occ)
        if len(merged) < len(occs):
            logger.info(
                "%s line %d: merged %d segments -> %d (consecutive split)",
                track_id, li, len(occs), len(merged),
            )
        matched_timing[li] = merged

    # ── Step 2: Create fused entries for ALL canonical lines ──
    fused_timeline: list[FusedTimelineEntry] = []
    track_overrides = semantic_overrides.get(track_id, {})

    for li, base_sem_line in enumerate(lines):
        # Apply per-line overrides
        line_override = (
            track_overrides.get(str(li))
            or track_overrides.get(li)
        )
        sem_line = {**base_sem_line, **(line_override or {})}
        media_queries = sem_line.get("media_queries", [])

        lyric_text = sem_line.get("lyric", "")

        if li in matched_timing:
            # Line has Whisper match(es) — create entry for each occurrence
            for occ_data in matched_timing[li]:
                start, end = occ_data["start"], occ_data["end"]
                # Use real Whisper word timestamps (like old pipeline),
                # fall back to synthesis only if no Whisper data available.
                whisper_in_range = words_for_range(all_words, start, end)
                if whisper_in_range:
                    words = [
                        WordTiming(start=w["start"], end=w["end"], text=w["text"])
                        for w in whisper_in_range
                    ]
                else:
                    words = synthesize_words_from_lyric(lyric_text, start, end)
                media = build_media_array(media_queries, start, end, manifest, beats=track_beats)

                fused_timeline.append(FusedTimelineEntry(
                    id=occ_data["id"],
                    start=start,
                    end=end,
                    lyric=lyric_text,
                    real_meaning=sem_line.get("real_meaning", ""),
                    media=media,
                    words=words,
                ))
        else:
            # Line has NO Whisper match — interpolate timing, synthetic words
            start, end = _interpolate_timing(li, len(lines), matched_timing)
            words = synthesize_words_from_lyric(lyric_text, start, end)
            media = build_media_array(media_queries, start, end, manifest, beats=track_beats)

            fused_timeline.append(FusedTimelineEntry(
                id=f"line_{li}_interp",
                start=start,
                end=end,
                lyric=lyric_text,
                real_meaning=sem_line.get("real_meaning", ""),
                media=media,
                words=words,
            ))

    # ── Step 3: Add instrumental entries that don't overlap ──
    for inst_entry in instrumental_entries:
        inst_start = inst_entry["start"]
        inst_end = inst_entry["end"]

        # Skip if it overlaps with any lyric entry
        overlaps = any(
            fe.start < inst_end and fe.end > inst_start
            for fe in fused_timeline
        )
        if overlaps:
            continue

        # Resolve context for instrumental segment
        meaning, mq = _resolve_instrumental_context(
            inst_entry, lines, semantic_index,
        )
        media = build_media_array(mq, inst_start, inst_end, manifest, beats=track_beats)
        inst_lyric = inst_entry.get("lyric", "")
        whisper_in_range = words_for_range(all_words, inst_start, inst_end)
        words = [
            WordTiming(start=w["start"], end=w["end"], text=w["text"])
            for w in whisper_in_range
        ]

        fused_timeline.append(FusedTimelineEntry(
            id=inst_entry["id"],
            start=inst_start,
            end=inst_end,
            lyric=inst_lyric,
            real_meaning=meaning,
            media=media,
            words=words,
        ))

    # ── Step 4: Sort everything by start time ──
    fused_timeline.sort(key=lambda e: e.start)

    return FusedTrackData(
        id=track_id,
        album_id=album_id,
        timeline=fused_timeline,
    )


def _resolve_instrumental_context(
    entry: dict[str, Any],
    lines: list[dict[str, Any]],
    semantic_index: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    """Resolve meaning and media for an instrumental/unmatched segment.

    Two-level fallback:
    1. Global semantic match by lyric text
    2. Default "Instrumental / ambience"
    """
    # Level 1: Global cross-track semantic match
    global_match = best_semantic_for_lyric(semantic_index, entry.get("lyric", ""))
    if global_match and global_match.get("semantic_line"):
        sl = global_match["semantic_line"]
        return (
            sl.get("real_meaning", "Instrumental / ambience"),
            sl.get("media_queries", []),
        )

    # Level 2: Default
    return "Instrumental / ambience", []


# ── Public API ──────────────────────────────────────────


def fuse_album_tracks(
    album_dir: Path,
    config: PipelineConfig,
    *,
    track_id: str | None = None,
) -> list[FusedTrackData]:
    """Fuse all (or one) tracks in an album.

    Combines timeline + semantics + alignment words + media manifest
    into player-ready track data objects.
    """
    project_root = config.project_root
    album_id = album_dir.name

    semantic_matrix = load_semantic_matrix(project_root, album_dir)
    semantic_index = build_semantic_index(semantic_matrix)
    semantic_overrides = load_semantic_overrides(project_root)
    manifest = load_manifest(album_dir)

    if manifest:
        ok_count = sum(
            1 for c in manifest.get("concepts", {}).values()
            if c.get("status") == "ok"
        )
        total = len(manifest.get("concepts", {}))
        if ok_count == 0 and total > 0:
            logger.warning(
                "Media manifest has %d concepts but NONE are 'ok'. "
                "All media arrays will be empty. Run media-fetch first.",
                total,
            )

    results: list[FusedTrackData] = []

    if track_id:
        obj = build_track_object(
            album_dir, album_id, semantic_matrix, semantic_index,
            track_id, semantic_overrides, manifest, config,
        )
        results.append(obj)
    else:
        data_dir = album_dir / "data"
        timeline_files = sorted(
            f for f in data_dir.iterdir()
            if f.suffix == ".json" and f.stem.endswith(".timeline")
        ) if data_dir.exists() else []

        if not timeline_files:
            raise FileNotFoundError(f"No .timeline.json files found in {data_dir}")

        for f in timeline_files:
            tid = f.stem.replace(".timeline", "")
            logger.info("Fusing %s...", tid)
            obj = build_track_object(
                album_dir, album_id, semantic_matrix, semantic_index,
                tid, semantic_overrides, manifest, config,
            )
            results.append(obj)

    logger.info("Fusion complete: %d tracks fused", len(results))
    return results
