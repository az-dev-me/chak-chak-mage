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


def load_timeline(album_dir: Path, track_id: str, variant_id: str | None = None) -> dict[str, Any]:
    """Load timeline JSON for a track (or variant)."""
    stem = f"{track_id}_{variant_id}" if variant_id else track_id
    path = album_dir / "data" / f"{stem}.timeline.json"
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
    variant_id: str | None = None,
) -> dict[str, Any] | None:
    """Load word-level Whisper alignment for a track (or variant), if available."""
    alignment_dir = album_dir.parent / "alignment"
    stem = f"{track_id}_{variant_id}" if variant_id else track_id
    path = alignment_dir / f"{stem}_words.json"
    if not path.exists():
        if variant_id:
            # Fall back to base track alignment
            base_path = alignment_dir / f"{track_id}_words.json"
            if base_path.exists():
                try:
                    return load_json(base_path)
                except (ValueError, FileNotFoundError):
                    return None
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


def build_segment_word_index(
    alignment: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Build a mapping from canonical lyric text → list of segment occurrences.

    Each alignment segment has a `text` field (the canonical line) and a
    `words` list. This builds a lookup so the fuse stage can grab the
    exact words for a canonical line without time-range slicing.

    Returns {text: [{"words": [...], "start": float, "end": float}, ...]}.
    Multiple occurrences (chorus repeats) are stored as separate entries.

    Only canonical-source words are included (ad-libs are filtered out
    to prevent chorus repeats / stray words from corrupting the display).
    """
    index: dict[str, list[dict[str, Any]]] = {}
    for seg in alignment.get("segments", []):
        text = seg.get("text", "").strip()
        if not text:
            continue
        words = []
        for w in seg.get("words", []):
            # Only include canonical words — ad-libs are unreliable
            # (often chorus repeats or stray detections)
            if w.get("source") == "ad-lib":
                continue
            words.append({
                "start": w["start"],
                "end": w["end"],
                "text": w.get("text", w.get("word", "")),
            })
        if words:
            index.setdefault(text, []).append({
                "words": words,
                "start": seg["start"],
                "end": seg["end"],
            })
    return index


def build_segment_all_words_index(
    alignment: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Build a mapping from canonical lyric text → list of ALL-word occurrences.

    Unlike build_segment_word_index (canonical-only), this includes ad-libs
    so they can serve as timing anchors for hybrid word timing.
    Returns {text: [{"words": [...], "start": float, "end": float}, ...]}.
    Multiple occurrences (chorus repeats) are stored as separate entries.
    """
    index: dict[str, list[dict[str, Any]]] = {}
    for seg in alignment.get("segments", []):
        text = seg.get("text", "").strip()
        if not text:
            continue
        words = []
        for w in seg.get("words", []):
            words.append({
                "start": w["start"],
                "end": w["end"],
                "text": w.get("text", w.get("word", "")),
                "source": w.get("source", ""),
            })
        if words:
            index.setdefault(text, []).append({
                "words": words,
                "start": seg["start"],
                "end": seg["end"],
            })
    return index


def _pick_best_occurrence(
    occurrences: list[dict[str, Any]],
    target_start: float,
    target_end: float,
) -> dict[str, Any] | None:
    """Pick the occurrence whose time range best overlaps the target range.

    When the same lyric appears multiple times (chorus repeats), each
    occurrence has different alignment timestamps. We pick the one whose
    segment range is closest to the fused entry's matched timing.
    """
    if not occurrences:
        return None
    if len(occurrences) == 1:
        return occurrences[0]

    best = None
    best_score = -1.0
    for occ in occurrences:
        occ_start = occ["start"]
        occ_end = occ["end"]
        # Score by overlap with target range
        overlap_start = max(occ_start, target_start)
        overlap_end = min(occ_end, target_end)
        overlap = max(0.0, overlap_end - overlap_start)
        # Also consider proximity (distance between midpoints)
        occ_mid = (occ_start + occ_end) / 2
        target_mid = (target_start + target_end) / 2
        proximity = 1.0 / (1.0 + abs(occ_mid - target_mid))
        score = overlap + proximity
        if score > best_score:
            best_score = score
            best = occ
    return best


def _clean_word(text: str) -> str:
    """Normalize a word for comparison: lowercase, strip punctuation."""
    return text.strip().lower().rstrip(".,!?;:'\"()-").lstrip("'\"(")


def hybrid_words_from_partial(
    lyric: str,
    seg_info: dict[str, Any],
) -> list[WordTiming]:
    """Build word timings using available words as anchors, interpolating gaps.

    Maps segment words (canonical + ad-lib) to positions in the canonical
    text by text matching. Uses matched words as timing anchors, interpolates
    unmatched positions proportionally between surrounding anchors.

    This preserves the natural singing rhythm for words we DO have timestamps
    for, while distributing the rest naturally in between.
    """
    canonical_texts = lyric.split()
    n = len(canonical_texts)
    if not canonical_texts:
        return []

    seg_words = seg_info["words"]
    seg_start = seg_info["start"]
    seg_end = seg_info["end"]

    if not seg_words:
        return synthesize_words_from_lyric(lyric, seg_start, seg_end)

    # Map each segment word to its best position in canonical text
    anchors: dict[int, dict[str, float]] = {}  # position → {start, end}
    used_positions: set[int] = set()

    for sw in seg_words:
        sw_clean = _clean_word(sw["text"])
        if not sw_clean:
            continue
        # Find first unmatched position whose text matches
        for pos in range(n):
            if pos in used_positions:
                continue
            if _clean_word(canonical_texts[pos]) == sw_clean:
                anchors[pos] = {"start": sw["start"], "end": sw["end"]}
                used_positions.add(pos)
                break

    if not anchors:
        return synthesize_words_from_lyric(lyric, seg_start, seg_end)

    sorted_anchor_positions = sorted(anchors.keys())

    result: list[WordTiming] = []
    for i in range(n):
        if i in anchors:
            result.append(WordTiming(
                start=round(anchors[i]["start"], 3),
                end=round(anchors[i]["end"], 3),
                text=canonical_texts[i],
            ))
        else:
            # Interpolate between surrounding anchors (or segment boundaries)
            prev_pos = None
            next_pos = None
            for ap in sorted_anchor_positions:
                if ap < i:
                    prev_pos = ap
                elif ap > i:
                    next_pos = ap
                    break

            # Determine interpolation range
            if prev_pos is not None:
                range_start = anchors[prev_pos]["end"]
                gap_start_idx = prev_pos + 1
            else:
                range_start = seg_start
                gap_start_idx = 0

            if next_pos is not None:
                range_end = anchors[next_pos]["start"]
                gap_end_idx = next_pos
            else:
                range_end = seg_end
                gap_end_idx = n

            gap_count = max(1, gap_end_idx - gap_start_idx)
            position_in_gap = i - gap_start_idx
            per_word = (range_end - range_start) / gap_count

            ws = round(range_start + per_word * position_in_gap, 3)
            we = round(range_start + per_word * (position_in_gap + 1), 3)
            result.append(WordTiming(start=ws, end=we, text=canonical_texts[i]))

    return result


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
    structure: dict[str, Any] | None = None,
) -> list[MediaEntry]:
    """Build media entries for a timeline segment.

    Uses musical structure analysis for emotionally intelligent pacing:
    - High energy: rapid image cycling (1-4s hold)
    - Low energy: images breathe (8-15s hold)
    - Section boundaries: new establishing shots
    Falls back to beat-based or even distribution when no structure data.
    """
    if not media_queries:
        return []

    from chak.utils.beats import beats_in_range

    duration = max(0.0, end - start)
    line_beats = beats_in_range(beats, start, end) if beats else []

    if structure:
        # Structure-aware pacing
        from chak.utils.structure import get_avg_intensity
        avg_intensity = get_avg_intensity(structure, start, end)

        # Map intensity to hold duration:
        # intensity 0.0 → 15s, intensity 1.0 → 1.5s
        min_hold = 1.5
        max_hold = 15.0
        hold_duration = max_hold - avg_intensity * (max_hold - min_hold)

        # Limit images to what fits within the line at this hold pace.
        # Short lines (2-3s) at high energy (hold ~3.5s) → 1 image held steady.
        # Longer lines or calmer sections → 2-3 images with room to breathe.
        max_fit = max(1, int(duration / hold_duration) + 1)
        n_images = min(len(media_queries), max_fit)

        # Space images at hold_duration intervals, snapped to nearest beat
        if n_images == 1:
            offsets = [0.0]
        elif line_beats and n_images > 1:
            offsets = [0.0]
            for k in range(1, n_images):
                abs_target = start + hold_duration * k
                nearest = min(line_beats, key=lambda b: abs(b - abs_target))
                offsets.append(round(nearest - start, 2))
        else:
            offsets = [round(hold_duration * i, 2) for i in range(n_images)]

        selected_queries = media_queries[:n_images]
    elif line_beats:
        # Beat-aware fallback (no structure data) — use all queries
        n_images = len(media_queries)
        selected_queries = media_queries
        # Place transitions at beats, pad with even spacing if not enough beats
        if len(line_beats) >= n_images - 1:
            offsets = [0.0] + [round(b - start, 2) for b in line_beats[:n_images - 1]]
        else:
            step = duration / n_images if n_images > 1 else 0.0
            offsets = [round(step * i, 2) for i in range(n_images)]
    else:
        # Even distribution fallback
        selected_queries = media_queries
        n_images = len(selected_queries)
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


def _pick_distributed_beats(
    beats: list[float],
    n: int,
) -> list[float]:
    """Pick n beats that are as evenly distributed as possible."""
    if n <= 0 or not beats:
        return []
    if n >= len(beats):
        return beats[:n]
    # Pick evenly spaced indices
    step = len(beats) / n
    return [beats[int(i * step)] for i in range(n)]


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
            # Use the latest occurrence that ends before or near this position
            best = max(occ["end"] for occ in matched_timing[j])
            prev_end = best
            break

    # Find nearest matched line AFTER this one — pick the occurrence
    # that starts AFTER prev_end (not the earliest overall, which may
    # be from an earlier repeat/chorus).
    next_start = None
    for j in range(line_index + 1, num_lines):
        if j in matched_timing:
            for occ in sorted(matched_timing[j], key=lambda o: o["start"]):
                if occ["start"] >= prev_end:
                    next_start = occ["start"]
                    break
            if next_start is not None:
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
        # No matched line after — space trailing unmatched lines evenly.
        # Find the contiguous trailing gap to assign each line a position.
        gap_first = line_index
        while gap_first > 0 and (gap_first - 1) not in matched_timing:
            gap_first -= 1
        total_in_gap = num_lines - gap_first
        position = line_index - gap_first
        per_line = 3.5  # typical singing line duration
        start = round(prev_end + per_line * position, 2)
        end = round(start + per_line, 2)
    else:
        # next_start <= prev_end (shouldn't happen)
        start = round(prev_end + 0.1, 2)
        end = round(start + 1.0, 2)

    return start, end


import re

_SENTENCE_SPLIT_RE = re.compile(
    r'(?<=[.!?;:])\s+'   # split after sentence-ending punctuation
    r'|'
    r'(?<=\)),\s+'        # split after closing paren + comma
)

MAX_DISPLAY_WORDS = 8


def _split_long_entries(
    timeline: list[FusedTimelineEntry],
    max_words: int = MAX_DISPLAY_WORDS,
) -> list[FusedTimelineEntry]:
    """Split timeline entries with too many words into sentence-level chunks.

    Long narration paragraphs are broken at sentence boundaries so the
    player displays one sentence at a time instead of a text wall.
    Loops until ALL entries are within max_words.
    """
    changed = True
    while changed:
        changed = False
        result: list[FusedTimelineEntry] = []

        for entry in timeline:
            words = entry.words
            if len(words) <= max_words:
                result.append(entry)
                continue

            changed = True

            # Split the lyric text into sentence-level chunks
            chunks = _SENTENCE_SPLIT_RE.split(entry.lyric)
            # If regex didn't split (no sentence boundaries), try comma
            if len(chunks) <= 1:
                chunks = [c.strip() for c in entry.lyric.split(', ') if c.strip()]
            # If still just one chunk, split by word count
            if len(chunks) <= 1:
                chunks = _split_by_word_count(entry.lyric, max_words)

            if len(chunks) <= 1:
                result.append(entry)
                changed = False  # Can't split further
                continue

            # Assign words to chunks by matching word texts
            word_idx = 0
            for ci, chunk in enumerate(chunks):
                chunk_word_texts = chunk.split()
                n = len(chunk_word_texts)

                chunk_words = list(words[word_idx:word_idx + n])
                word_idx += n

                if not chunk_words:
                    continue

                # Realign word texts to match chunk text (splitting
                # at commas strips trailing punctuation from lyric)
                for wi, cwt in enumerate(chunk_word_texts):
                    if wi < len(chunk_words) and chunk_words[wi].text != cwt:
                        chunk_words[wi] = WordTiming(
                            start=chunk_words[wi].start,
                            end=chunk_words[wi].end,
                            text=cwt,
                        )

                chunk_start = chunk_words[0].start
                chunk_end = chunk_words[-1].end

                # Distribute media to chunks by offset time range
                chunk_media = [m for m in entry.media
                               if chunk_start <= entry.start + m.offset < chunk_end] if entry.media else []
                chunk_hidden = [m for m in entry.hidden_media
                                if chunk_start <= entry.start + m.offset < chunk_end] if entry.hidden_media else []
                # First chunk always gets at least the first image (fallback)
                if ci == 0 and not chunk_media and entry.media:
                    chunk_media = [entry.media[0]]
                if ci == 0 and not chunk_hidden and entry.hidden_media:
                    chunk_hidden = [entry.hidden_media[0]]
                chunk_meaning = entry.real_meaning if ci == 0 else ""

                result.append(FusedTimelineEntry(
                    id=f"{entry.id}_s{ci}",
                    start=chunk_start,
                    end=chunk_end,
                    lyric=chunk,
                    real_meaning=chunk_meaning,
                    media=chunk_media,
                    hidden_media=chunk_hidden,
                    words=chunk_words,
                ))

        timeline = result

    return timeline


def _split_by_word_count(text: str, max_words: int) -> list[str]:
    """Split text into chunks of approximately *max_words* words."""
    all_words = text.split()
    chunks = []
    for i in range(0, len(all_words), max_words):
        chunk = " ".join(all_words[i:i + max_words])
        chunks.append(chunk)
    return chunks


MIN_ENTRY_DURATION = 0.3  # Absolute minimum seconds per entry


def _enforce_minimum_duration(
    timeline: list[FusedTimelineEntry],
) -> list[FusedTimelineEntry]:
    """Spread out zero/tiny-duration entries that pile up at the same time.

    When the timeline stage matches multiple lines to the same point (e.g.
    all at 12.1s), the fused entries have zero duration and overlap. This
    spreads them evenly across the gap to the next distinct entry.
    """
    if not timeline:
        return timeline

    # Sort by start time first
    timeline.sort(key=lambda e: e.start)

    # Find clusters of entries with identical or near-identical start times
    i = 0
    while i < len(timeline):
        # Find consecutive entries that start within 0.1s — cluster even
        # if some have non-zero duration (they need re-spacing too)
        cluster_start = i
        cluster_end = i + 1
        needs_fix = timeline[i].end - timeline[i].start < MIN_ENTRY_DURATION
        while (
            cluster_end < len(timeline)
            and timeline[cluster_end].start - timeline[cluster_start].start < 0.1
        ):
            dur = timeline[cluster_end].end - timeline[cluster_end].start
            if dur < MIN_ENTRY_DURATION:
                needs_fix = True
            cluster_end += 1

        # Also mark as needing fix if all entries share same start+end
        # (stacked interpolated entries)
        if cluster_end - cluster_start > 1 and not needs_fix:
            starts = {round(timeline[j].start, 2) for j in range(cluster_start, cluster_end)}
            ends = {round(timeline[j].end, 2) for j in range(cluster_start, cluster_end)}
            if len(starts) == 1 and len(ends) == 1:
                needs_fix = True

        cluster_size = cluster_end - cluster_start
        if cluster_size > 1 and needs_fix:
            # Multiple entries piled up — spread them out
            range_start = timeline[cluster_start].start
            # Find the next entry after the cluster for the upper bound
            if cluster_end < len(timeline):
                range_end = timeline[cluster_end].start
            else:
                # Last cluster — estimate duration
                range_end = range_start + cluster_size * 2.0

            if range_end <= range_start:
                range_end = range_start + cluster_size * 2.0

            per_entry = (range_end - range_start) / cluster_size

            for ci in range(cluster_size):
                idx = cluster_start + ci
                entry = timeline[idx]
                new_start = round(range_start + per_entry * ci, 3)
                new_end = round(range_start + per_entry * (ci + 1), 3)

                # Rebuild word timings for the new range
                new_words = synthesize_words_from_lyric(
                    entry.lyric, new_start, new_end,
                )

                timeline[idx] = FusedTimelineEntry(
                    id=entry.id,
                    start=new_start,
                    end=new_end,
                    lyric=entry.lyric,
                    real_meaning=entry.real_meaning,
                    media=entry.media,
                    hidden_media=entry.hidden_media,
                    words=new_words,
                )

            i = cluster_end
        elif (
            timeline[i].end - timeline[i].start < MIN_ENTRY_DURATION
            and len(timeline[i].words) > 0
        ):
            # Single entry with too-short duration
            entry = timeline[i]
            n_words = len(entry.lyric.split()) if entry.lyric else 1
            min_dur = max(MIN_ENTRY_DURATION, n_words * 0.25)
            new_end = entry.start + min_dur

            # Don't overlap with next entry
            if i + 1 < len(timeline) and new_end > timeline[i + 1].start:
                new_end = timeline[i + 1].start

            if new_end > entry.start:
                new_words = synthesize_words_from_lyric(
                    entry.lyric, entry.start, new_end,
                )
                timeline[i] = FusedTimelineEntry(
                    id=entry.id,
                    start=entry.start,
                    end=round(new_end, 3),
                    lyric=entry.lyric,
                    real_meaning=entry.real_meaning,
                    media=entry.media,
                    hidden_media=entry.hidden_media,
                    words=new_words,
                )
            i += 1
        else:
            i += 1

    return timeline


def _resolve_overlaps(
    timeline: list[FusedTimelineEntry],
) -> list[FusedTimelineEntry]:
    """Resolve overlapping entries by clipping earlier entries.

    When timeline matching produces overlapping entries (e.g., from loose
    similarity thresholds), clip the earlier entry's end to the later
    entry's start so no two entries overlap in the player.
    """
    if len(timeline) < 2:
        return timeline

    timeline.sort(key=lambda e: e.start)

    for i in range(len(timeline) - 1):
        if timeline[i].end > timeline[i + 1].start:
            entry = timeline[i]
            new_end = timeline[i + 1].start
            if new_end <= entry.start:
                new_end = entry.start + 0.1  # minimal duration
            timeline[i] = FusedTimelineEntry(
                id=entry.id,
                start=entry.start,
                end=round(new_end, 3),
                lyric=entry.lyric,
                real_meaning=entry.real_meaning,
                media=entry.media,
                hidden_media=entry.hidden_media,
                words=synthesize_words_from_lyric(entry.lyric, entry.start, new_end),
            )

    return timeline


# ── Variant lyrics helpers ─────────────────────────────


def _load_variant_lyrics(
    project_root: Path, track_id: str, variant_id: str,
) -> list[str] | None:
    """Load variant-specific lyrics from shared/semantics/lyrics/."""
    lyrics_dir = project_root / "shared" / "semantics" / "lyrics"
    lyrics_file = lyrics_dir / f"{track_id}_{variant_id}.txt"
    if not lyrics_file.exists():
        return None
    text = lyrics_file.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _build_variant_sem_lines(
    variant_lyrics: list[str],
    base_sem_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create synthetic semantic lines from variant lyrics.

    Reuses the base track's images by cycling through them.
    Variant lines get no ``real_meaning`` (no parallel narrative).
    """
    synthetic: list[dict[str, Any]] = []
    n_base = len(base_sem_lines) if base_sem_lines else 1
    for i, lyric in enumerate(variant_lyrics):
        base_idx = i % n_base if base_sem_lines else 0
        base = base_sem_lines[base_idx] if base_sem_lines else {}
        synthetic.append({
            "lyric": lyric,
            "media_queries": base.get("media_queries", []),
            "hidden_media_queries": base.get("hidden_media_queries", []),
            "real_meaning": "",
        })
    return synthetic


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
    variant_id: str | None = None,
) -> FusedTrackData:
    """Build a complete fused track object for the player.

    LYRICS-DRIVEN: iterates over ALL canonical lines from the semantic
    matrix, guaranteeing every lyric appears in the player output.
    Lines without Whisper matches get interpolated timing.

    When *variant_id* is given, reads variant-qualified timeline/alignment/
    structure files but uses bare *track_id* for semantic matrix lookup.
    """
    # Semantic lookup always uses bare track_id (same lyrics/images)
    sem_track = semantic_matrix.get(track_id)
    if not sem_track:
        raise ValueError(f"No semantic data found for {track_id}")

    # File stem for variant-qualified data files
    file_stem = f"{track_id}_{variant_id}" if variant_id else track_id
    label = f"{track_id}/{variant_id}" if variant_id else track_id

    base_timeline_data = load_timeline(album_dir, track_id, variant_id)
    base_timeline = base_timeline_data.get("timeline", [])
    base_sem_lines = sem_track.get("lines", [])

    # Check if variant has its own lyrics (different from semantic matrix)
    lines = base_sem_lines
    if variant_id:
        variant_lyrics = _load_variant_lyrics(config.project_root, track_id, variant_id)
        if variant_lyrics and len(variant_lyrics) != len(base_sem_lines):
            logger.info(
                "%s: Variant %s has %d lyrics lines vs %d semantic lines — "
                "using variant lyrics with recycled images",
                track_id, variant_id, len(variant_lyrics), len(base_sem_lines),
            )
            lines = _build_variant_sem_lines(variant_lyrics, base_sem_lines)

    # ── Step 0: Load Whisper word-level alignment (if available) ──
    alignment = load_alignment_for_track(album_dir, track_id, variant_id)
    all_words = flatten_words(alignment) if alignment else []
    seg_word_index = build_segment_word_index(alignment) if alignment else {}
    seg_all_index = build_segment_all_words_index(alignment) if alignment else {}
    if all_words:
        logger.info(
            "%s: loaded %d Whisper words for karaoke timing",
            label, len(all_words),
        )

    # ── Step 0b: Load beat data (if available) ──
    from chak.utils.beats import load_beats
    track_beats = load_beats(track_id, album_dir)
    if track_beats:
        logger.info(
            "%s: loaded %d beat timestamps for media sync",
            label, len(track_beats),
        )

    # ── Step 0c: Load musical structure analysis (if available) ──
    from chak.utils.structure import load_structure
    track_structure = load_structure(track_id, album_dir, variant_id)
    if track_structure:
        logger.info(
            "%s: loaded structure data (%d sections, %d transitions)",
            label,
            len(track_structure.get("sections", [])),
            len(track_structure.get("transition_points", [])),
        )
        # Prefer structure beat_times over standalone .beats.json (may be stale)
        struct_beats = track_structure.get("beat_times", [])
        if struct_beats:
            logger.info(
                "%s: using %d beats from structure (was %d from .beats.json)",
                label, len(struct_beats), len(track_beats),
            )
            track_beats = struct_beats

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

    # Filter out failed alignment segments from matched_timing.
    # Criteria: zero-duration OR too compressed for the line's word count.
    # When stable-ts can't align a segment, it sets start ≈ end (usually
    # at the audio end). These should fall through to interpolation.
    for li in list(matched_timing.keys()):
        lyric = lines[li].get("lyric", "") if li < len(lines) else ""
        n_words = max(1, len(lyric.split()))
        min_duration = max(0.05, n_words * 0.1)  # at least 0.1s/word
        matched_timing[li] = [
            occ for occ in matched_timing[li]
            if abs(occ["end"] - occ["start"]) >= min_duration
        ]
        if not matched_timing[li]:
            del matched_timing[li]

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
        hidden_media_queries = sem_line.get("hidden_media_queries", [])

        lyric_text = sem_line.get("lyric", "")

        if li in matched_timing:
            # Line has Whisper match(es) — create entry for each occurrence
            for occ_data in matched_timing[li]:
                start, end = occ_data["start"], occ_data["end"]
                # Prefer segment words (exact per-line alignment) over
                # time-range slicing which can bleed across lines.
                # Pick the occurrence whose time range matches this entry.
                seg_occs = seg_word_index.get(lyric_text, [])
                seg_best = _pick_best_occurrence(seg_occs, start, end)
                seg_words = seg_best["words"] if seg_best else []
                lyric_word_count = len(lyric_text.split()) if lyric_text else 0
                if seg_words and len(seg_words) >= lyric_word_count * 0.7:
                    # Good canonical coverage — use them directly
                    words = [
                        WordTiming(start=w["start"], end=w["end"], text=w["text"])
                        for w in seg_words
                    ]
                    # Pad missing tail words (when seg was clipped short)
                    if len(words) < lyric_word_count and lyric_text:
                        canon_texts = lyric_text.split()
                        tail_start = words[-1].end
                        tail_end = end
                        tail_texts = canon_texts[len(words):]
                        if tail_texts:
                            # If no room, extend by 0.3s per missing word
                            if tail_end <= tail_start:
                                tail_end = tail_start + len(tail_texts) * 0.3
                            per_w = (tail_end - tail_start) / len(tail_texts)
                            for ti, tw in enumerate(tail_texts):
                                words.append(WordTiming(
                                    start=round(tail_start + per_w * ti, 3),
                                    end=round(tail_start + per_w * (ti + 1), 3),
                                    text=tw,
                                ))
                else:
                    # Try hybrid: use ALL words (canonical + ad-lib) as
                    # timing anchors and interpolate the gaps naturally.
                    all_occs = seg_all_index.get(lyric_text, [])
                    seg_all = _pick_best_occurrence(all_occs, start, end)
                    if seg_all and seg_all["words"]:
                        words = hybrid_words_from_partial(lyric_text, seg_all)
                    else:
                        words = synthesize_words_from_lyric(lyric_text, start, end)
                # Adjust entry timing to match actual word boundaries:
                # - Tighten START: segments can start early due to ad-libs
                #   (e.g. "dum dum" before the lyric), causing text to
                #   appear too early.
                # - Extend END: timeline may clip end to first canonical
                #   word, but hybrid timing fills the full segment range.
                if words:
                    word_start = words[0].start
                    word_end = words[-1].end
                    if word_start > start + 0.5:
                        start = round(word_start - 0.2, 3)  # small pre-roll
                    if word_end > end + 0.1:
                        end = round(word_end, 3)

                media = build_media_array(media_queries, start, end, manifest, beats=track_beats, structure=track_structure)
                hidden_media = build_media_array(hidden_media_queries, start, end, manifest, beats=track_beats, structure=track_structure)

                fused_timeline.append(FusedTimelineEntry(
                    id=occ_data["id"],
                    start=start,
                    end=end,
                    lyric=lyric_text,
                    real_meaning=sem_line.get("real_meaning", ""),
                    media=media,
                    hidden_media=hidden_media,
                    words=words,
                ))
        else:
            # Line has NO Whisper match — interpolate timing, synthetic words
            start, end = _interpolate_timing(li, len(lines), matched_timing)
            duration = end - start
            n_words = max(1, len(lyric_text.split()))
            # Minimum: 0.15s per word, at least 0.8s total
            min_required = max(0.8, n_words * 0.15)

            if duration < min_required:
                # Gap too small — this line wasn't sung, skip it
                logger.info(
                    "%s: Dropping unmatched line %d (%.2fs for %d words): %.60s",
                    label, li, duration, n_words, lyric_text,
                )
                continue

            words = synthesize_words_from_lyric(lyric_text, start, end)
            media = build_media_array(media_queries, start, end, manifest, beats=track_beats, structure=track_structure)
            hidden_media = build_media_array(hidden_media_queries, start, end, manifest, beats=track_beats, structure=track_structure)

            fused_timeline.append(FusedTimelineEntry(
                id=f"line_{li}_interp",
                start=start,
                end=end,
                lyric=lyric_text,
                real_meaning=sem_line.get("real_meaning", ""),
                media=media,
                hidden_media=hidden_media,
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
        media = build_media_array(mq, inst_start, inst_end, manifest, beats=track_beats, structure=track_structure)
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
            hidden_media=[],
            words=words,
        ))

    # ── Step 3b: Split long entries into sentence-level chunks ──
    fused_timeline = _split_long_entries(fused_timeline)

    # ── Step 3c: Enforce minimum duration for zero/tiny entries ──
    fused_timeline = _enforce_minimum_duration(fused_timeline)

    # ── Step 3d: Resolve overlapping entries ──
    fused_timeline = _resolve_overlaps(fused_timeline)

    # ── Step 4: Sort everything by start time ──
    fused_timeline.sort(key=lambda e: e.start)

    # ── Step 5: Include beat & energy data for frontend sync ──
    beat_times_out: list[float] = []
    energy_curve_out: list[list[float]] = []
    bpm_out: float = 0.0

    sections_out: list[dict] = []
    transition_points_out: list[float] = []

    # track_beats already updated to structure beats in Step 0c
    if track_beats:
        beat_times_out = [round(b, 3) for b in track_beats]
    if track_structure:
        energy_curve_out = track_structure.get("energy_curve", [])
        bpm_out = track_structure.get("bpm", 0.0)
        sections_out = track_structure.get("sections", [])
        transition_points_out = [
            round(t, 3) for t in track_structure.get("transition_points", [])
        ]

    return FusedTrackData(
        id=file_stem,
        album_id=album_id,
        timeline=fused_timeline,
        beat_times=beat_times_out,
        energy_curve=energy_curve_out,
        bpm=bpm_out,
        sections=sections_out,
        transition_points=transition_points_out,
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
    variant_id: str | None = None,
) -> list[FusedTrackData]:
    """Fuse all (or one) tracks in an album.

    Combines timeline + semantics + alignment words + media manifest
    into player-ready track data objects.

    When *variant_id* is given (requires *track_id*), fuses with
    variant-qualified data files while using bare track_id for semantics.
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
            variant_id=variant_id,
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
            # Skip variant-qualified timelines (e.g. track_02_T2b) —
            # they are only fused via explicit --track/--variant flags.
            if tid not in semantic_matrix:
                logger.debug("Skipping variant timeline %s", f.name)
                continue
            logger.info("Fusing %s...", tid)
            obj = build_track_object(
                album_dir, album_id, semantic_matrix, semantic_index,
                tid, semantic_overrides, manifest, config,
            )
            results.append(obj)

    logger.info("Fusion complete: %d tracks fused", len(results))
    return results
