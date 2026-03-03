"""Stage 1: Audio alignment via stable-ts (Whisper wrapper).

Two-pass strategy for album tracks:
  Pass 1: Force-align canonical lyrics → rock-solid word timestamps
  Pass 2: Free transcription → discover ad-libs/vocalizations
  Merge:  Aligned words as ground truth, insert transcribed extras in gaps

For raw catalog alignment (no canonical lyrics): single-pass transcription
with anti-hallucination settings.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from chak.config import AlignmentConfig, PipelineConfig
from chak.schemas import AlignmentResult
from chak.utils.hallucination import filter_segments
from chak.utils.io import ensure_dir, load_json
from chak.utils.similarity import token_overlap
from chak.utils.text import normalize

logger = logging.getLogger(__name__)


def check_dependencies() -> bool:
    """Verify stable-ts and ffmpeg are available."""
    if shutil.which("ffmpeg") is None:
        logger.warning("ffmpeg is not installed or not in PATH.")
        return False
    try:
        import stable_whisper  # noqa: F401
    except ImportError:
        logger.warning(
            "stable-ts not installed. "
            "Install with: pip install stable-ts demucs"
        )
        return False
    return True


def _load_model(config: AlignmentConfig) -> Any:
    """Load stable-ts Whisper model (cached per session)."""
    import stable_whisper

    logger.info(
        "Loading stable-ts model '%s' on %s",
        config.whisper_model, config.whisper_device,
    )
    return stable_whisper.load_model(
        config.whisper_model,
        device=config.whisper_device,
    )


def _get_canonical_lyrics(project_root: Path, track_id: str) -> str | None:
    """Load canonical lyrics for a track from the semantic matrix.

    Returns all lyrics joined with newlines, or None if not found.
    """
    matrix_path = project_root / "shared" / "semantics" / "base_semantic_matrix.json"
    if not matrix_path.exists():
        return None

    matrix = load_json(matrix_path)
    track_data = matrix.get(track_id)
    if not track_data or not track_data.get("lines"):
        return None

    lyrics = []
    for line in track_data["lines"]:
        lyric = line.get("lyric", "").strip()
        if lyric:
            lyrics.append(lyric)

    return "\n".join(lyrics) if lyrics else None


def _extract_words_from_result(result: Any) -> list[dict[str, Any]]:
    """Extract flat word list from a stable-ts WhisperResult."""
    words = []
    for seg in result.segments:
        for w in seg.words:
            text = str(w.word).strip()
            if not text:
                continue
            words.append({
                "start": round(float(w.start), 3),
                "end": round(float(w.end), 3),
                "text": text,
            })
    return words


def _extract_segments_from_result(result: Any) -> list[dict[str, Any]]:
    """Extract segment list from a stable-ts WhisperResult."""
    segments = []
    for seg in result.segments:
        words_out = []
        for w in seg.words:
            text = str(w.word).strip()
            if not text:
                continue
            words_out.append({
                "start": round(float(w.start), 3),
                "end": round(float(w.end), 3),
                "text": text,
            })
        seg_text = str(seg.text).strip()
        if not seg_text or not words_out:
            continue
        segments.append({
            "start": round(float(seg.start), 3),
            "end": round(float(seg.end), 3),
            "text": seg_text,
            "words": words_out,
        })
    return segments


def _rescue_failed_words(
    aligned_words: list[dict[str, Any]],
    transcribed_words: list[dict[str, Any]],
    cluster_threshold: float = 0.15,
    min_cluster_size: int = 3,
) -> list[dict[str, Any]]:
    """Fix canonical words that stable-ts failed to align.

    When stable-ts can't align words, it crams them at the same timestamp
    (typically the end of audio or an arbitrary point). We detect these
    clusters and replace their timestamps with the free transcription's
    timestamps for matching text.

    A "stale cluster" is *min_cluster_size*+ consecutive words whose
    start times are all within *cluster_threshold* seconds of each other.
    """
    if not aligned_words or not transcribed_words:
        return aligned_words

    # ── Step 1: Detect stale clusters ──
    clusters: list[tuple[int, int]] = []  # (start_idx, end_idx) exclusive
    i = 0
    while i < len(aligned_words):
        anchor_time = aligned_words[i]["start"]
        j = i + 1
        while j < len(aligned_words) and abs(aligned_words[j]["start"] - anchor_time) <= cluster_threshold:
            j += 1
        if j - i >= min_cluster_size:
            clusters.append((i, j))
            i = j
        else:
            i += 1

    if not clusters:
        return aligned_words

    # ── Step 2: Build a text→timing lookup from transcription ──
    tw_by_text: dict[str, list[dict[str, Any]]] = {}
    for tw in transcribed_words:
        key = tw["text"].strip().lower().rstrip(".,!?;:'\"()-")
        tw_by_text.setdefault(key, []).append(tw)

    # ── Step 3: For each cluster, try to steal transcription timestamps ──
    rescued_count = 0
    for c_start, c_end in clusters:
        cluster_words = aligned_words[c_start:c_end]
        stale_time = cluster_words[0]["start"]

        # Try to match each word in the cluster to a transcribed word
        used_tw: set[int] = set()  # track used transcription word indices
        matches: list[tuple[int, dict]] = []  # (aligned_idx, transcribed_word)

        for ci, aw in enumerate(cluster_words):
            key = aw["text"].strip().lower().rstrip(".,!?;:'\"()-")
            candidates = tw_by_text.get(key, [])
            # Pick the candidate closest to the expected position
            # (either previous match's end, or chronological order)
            best = None
            best_dist = float("inf")
            for tw in candidates:
                tw_id = id(tw)
                if tw_id in used_tw:
                    continue
                # Prefer words that come AFTER previous matches
                if matches:
                    last_end = matches[-1][1]["end"]
                    if tw["start"] < last_end - 0.5:
                        continue
                    dist = tw["start"] - last_end
                else:
                    dist = abs(tw["start"] - stale_time)
                if dist < best_dist:
                    best_dist = dist
                    best = tw
            if best is not None:
                used_tw.add(id(best))
                matches.append((c_start + ci, best))

        # Apply rescued timestamps
        if len(matches) >= len(cluster_words) * 0.3:
            # Build anchor map from matches
            anchor_times: dict[int, tuple[float, float]] = {}
            for ai, tw in matches:
                anchor_times[ai] = (tw["start"], tw["end"])

            # Apply anchors directly
            for ai, (ts, te) in anchor_times.items():
                aligned_words[ai]["start"] = ts
                aligned_words[ai]["end"] = te
                rescued_count += 1

            # Interpolate non-matched words between anchors
            sorted_anchor_idxs = sorted(anchor_times.keys())
            for ci in range(c_start, c_end):
                if ci in anchor_times:
                    continue
                # Find surrounding anchors
                prev_a = None
                next_a = None
                for ai in sorted_anchor_idxs:
                    if ai < ci:
                        prev_a = ai
                    elif ai > ci:
                        next_a = ai
                        break

                if prev_a is not None:
                    range_start = anchor_times[prev_a][1]
                    gap_begin = prev_a + 1
                elif sorted_anchor_idxs:
                    range_start = anchor_times[sorted_anchor_idxs[0]][0] - 1.0
                    gap_begin = c_start
                else:
                    continue

                if next_a is not None:
                    range_end = anchor_times[next_a][0]
                    gap_finish = next_a
                elif sorted_anchor_idxs:
                    range_end = anchor_times[sorted_anchor_idxs[-1]][1] + 1.0
                    gap_finish = c_end
                else:
                    continue

                gap_count = max(1, gap_finish - gap_begin)
                pos = ci - gap_begin
                per_word = (range_end - range_start) / gap_count
                aligned_words[ci]["start"] = round(range_start + per_word * pos, 3)
                aligned_words[ci]["end"] = round(range_start + per_word * (pos + 1), 3)
                rescued_count += 1

        logger.info(
            "Rescued stale cluster of %d words at %.2fs (%d matched from transcription)",
            len(cluster_words), stale_time, len(matches),
        )

    if rescued_count:
        logger.info("Total rescued words: %d", rescued_count)

    return aligned_words


def _merge_aligned_and_transcribed(
    aligned_words: list[dict[str, Any]],
    transcribed_words: list[dict[str, Any]],
    gap_threshold: float = 0.1,
) -> list[dict[str, Any]]:
    """Merge force-aligned canonical words with freely-transcribed extras.

    Aligned words are ground truth. Transcribed words that fall in gaps
    between aligned words are kept as ad-libs/vocalizations.
    Transcribed words that overlap aligned words are discarded.
    """
    if not aligned_words:
        # No aligned data — use transcribed as-is
        for w in transcribed_words:
            w["source"] = "transcribed"
        return transcribed_words

    # Mark aligned words
    for w in aligned_words:
        w["source"] = "canonical"

    if not transcribed_words:
        return aligned_words

    merged = list(aligned_words)

    for tw in transcribed_words:
        tw_start = tw["start"]
        tw_end = tw["end"]

        # Check if this transcribed word overlaps any aligned word
        overlaps = False
        for aw in aligned_words:
            # Overlap if the time ranges intersect (with small tolerance)
            if tw_start < (aw["end"] + gap_threshold) and tw_end > (aw["start"] - gap_threshold):
                overlaps = True
                break

        if not overlaps:
            # Word is in a gap — likely an ad-lib or vocalization
            tw["source"] = "ad-lib"
            merged.append(tw)

    # Sort by start time
    merged.sort(key=lambda w: (w["start"], w.get("source") != "canonical"))
    return merged


def _cluster_canonical_words(
    words: list[dict[str, Any]],
    max_gap: float = 8.0,
    adlib_words: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Keep only contiguous clusters of canonical words.

    If consecutive canonical words have a gap > max_gap seconds AND
    the gap is NOT bridged by ad-lib words (breathing, vocalizations),
    stable-ts likely misplaced the later ones — clip there.

    When ad-libs exist inside a gap, the gap is genuine: the singer
    was producing non-lyric audio. We keep both sides.
    """
    if len(words) <= 1:
        return words

    adlibs = adlib_words or []

    for i in range(1, len(words)):
        gap = words[i]["start"] - words[i - 1]["end"]
        if gap > max_gap:
            # Check if ad-libs bridge this gap
            gap_start = words[i - 1]["end"]
            gap_end = words[i]["start"]
            bridged = any(
                a["start"] >= gap_start - 0.5 and a["end"] <= gap_end + 0.5
                for a in adlibs
            )
            if bridged:
                logger.debug(
                    "Gap of %.1fs between '%s' (%.2f) and '%s' (%.2f) "
                    "bridged by ad-libs — keeping both sides",
                    gap, words[i - 1]["text"], words[i - 1]["end"],
                    words[i]["text"], words[i]["start"],
                )
                continue

            logger.debug(
                "Clipping canonical words: gap of %.1fs between '%s' (%.2f) "
                "and '%s' (%.2f) with no ad-libs bridging",
                gap, words[i - 1]["text"], words[i - 1]["end"],
                words[i]["text"], words[i]["start"],
            )
            return words[:i]

    return words


def _nearby_adlibs(
    adlib_words: list[dict[str, Any]],
    canonical_words: list[dict[str, Any]],
    proximity: float = 2.0,
) -> list[dict[str, Any]]:
    """Return ad-lib words that are within *proximity* seconds of a canonical word."""
    if not canonical_words or not adlib_words:
        return []

    result = []
    for aw in adlib_words:
        aw_mid = (aw["start"] + aw["end"]) / 2
        for cw in canonical_words:
            # Check if ad-lib is near this canonical word
            if abs(aw_mid - cw["start"]) <= proximity or abs(aw_mid - cw["end"]) <= proximity:
                result.append(aw)
                break
    return result


def _repair_segment_word_timing(seg: dict[str, Any]) -> None:
    """Fix word timings within a segment when stable-ts produced bad timestamps.

    Detects two problems:
    1. Words with 0 or near-0 duration (< 0.03s) — crushed by overlap clipping
    2. Large internal gaps (> 2s) between consecutive words in the same line

    Uses words with reasonable timing as anchors and re-interpolates the rest
    proportionally within the segment boundaries — same strategy as
    hybrid_words_from_partial() in fuse.py.
    """
    words = seg.get("words", [])
    if len(words) < 2:
        return

    seg_start = seg["start"]
    seg_end = seg["end"]
    seg_duration = seg_end - seg_start
    if seg_duration <= 0:
        # 0-duration segment — all words crammed at one point.
        # Can't repair without knowing the real time range.
        # The rescue step should have fixed this; if not, skip.
        return

    # Identify reliable anchors: words with reasonable duration and no huge gaps
    min_duration = 0.03

    anchors: dict[int, dict] = {}
    bad_indices: list[int] = []
    for i, w in enumerate(words):
        dur = w["end"] - w["start"]
        if dur >= min_duration:
            anchors[i] = w
        else:
            bad_indices.append(i)

    # Nothing to fix
    if not bad_indices:
        return

    if not anchors:
        # All words are bad — evenly distribute
        per_word = seg_duration / len(words)
        for i, w in enumerate(words):
            w["start"] = round(seg_start + per_word * i, 3)
            w["end"] = round(seg_start + per_word * (i + 1), 3)
        return

    # Re-interpolate non-anchor words between surrounding anchors
    sorted_anchors = sorted(anchors.keys())

    for i, w in enumerate(words):
        if i in anchors:
            continue

        # Find surrounding anchors
        prev_anchor = None
        next_anchor = None
        for ai in sorted_anchors:
            if ai < i:
                prev_anchor = ai
            elif ai > i:
                next_anchor = ai
                break

        # Determine interpolation range
        if prev_anchor is not None:
            range_start = anchors[prev_anchor]["end"]
            gap_start_idx = prev_anchor + 1
        else:
            range_start = seg_start
            gap_start_idx = 0

        if next_anchor is not None:
            range_end = anchors[next_anchor]["start"]
            gap_end_idx = next_anchor
        else:
            range_end = seg_end
            gap_end_idx = len(words)

        gap_count = max(1, gap_end_idx - gap_start_idx)
        position_in_gap = i - gap_start_idx
        per_word = (range_end - range_start) / gap_count

        w["start"] = round(range_start + per_word * position_in_gap, 3)
        w["end"] = round(range_start + per_word * (position_in_gap + 1), 3)

        # Enforce minimum word duration (at least 0.04s)
        if w["end"] - w["start"] < 0.04:
            w["end"] = round(w["start"] + 0.04, 3)

    logger.debug(
        "Repaired word timing in segment '%.30s...' [%.2f-%.2f]",
        seg.get("text", ""), seg_start, seg_end,
    )


def _distribute_stale_tail_segments(segments: list[dict[str, Any]]) -> None:
    """Spread 0-duration segments crammed at the end of a track.

    When stable-ts fails to align the last N lines (e.g. repeated chorus),
    all those segments end up with identical start==end at the audio's end.
    We detect this tail and distribute those segments evenly in the gap
    between the last valid segment and the stale point.
    """
    if len(segments) < 2:
        return

    # Find how many trailing segments have 0 duration
    stale_count = 0
    stale_time = segments[-1]["start"]
    for i in range(len(segments) - 1, -1, -1):
        seg = segments[i]
        dur = seg["end"] - seg["start"]
        if dur < 0.05 and abs(seg["start"] - stale_time) < 0.5:
            stale_count += 1
        else:
            break

    if stale_count < 1:
        return

    last_valid_idx = len(segments) - stale_count - 1
    if last_valid_idx < 0:
        return

    last_valid = segments[last_valid_idx]
    gap_start = last_valid["end"]
    gap_end = stale_time  # the point they're all crammed at

    # Need at least some gap to distribute into
    if gap_end - gap_start < 1.0:
        # Not enough room — try to use last_valid's end to stale_time + small buffer
        gap_end = stale_time + stale_count * 2.0  # assume ~2s per line

    total_gap = gap_end - gap_start
    per_seg = total_gap / stale_count

    logger.info(
        "Distributing %d stale tail segments into [%.1f-%.1f] (%.1fs each)",
        stale_count, gap_start, gap_end, per_seg,
    )

    for i in range(stale_count):
        seg_idx = last_valid_idx + 1 + i
        seg = segments[seg_idx]
        new_start = round(gap_start + per_seg * i, 3)
        new_end = round(gap_start + per_seg * (i + 1), 3)
        seg["start"] = new_start
        seg["end"] = new_end

        # Evenly distribute words within the new time range
        words = seg.get("words", [])
        if words:
            word_dur = (new_end - new_start) / len(words)
            for wi, w in enumerate(words):
                w["start"] = round(new_start + word_dur * wi, 3)
                w["end"] = round(new_start + word_dur * (wi + 1), 3)


def _build_segments_per_line(
    merged_words: list[dict[str, Any]],
    canonical_lines: list[str],
    max_canonical_gap: float = 5.0,
    adlib_proximity: float = 2.0,
) -> list[dict[str, Any]]:
    """Build one segment per canonical line by assigning words to lines.

    Since the words came from force-aligning the canonical lyrics in order,
    we walk through both lists together: each canonical line's word count
    tells us how many aligned words belong to that segment.

    Two safeguards against misalignment:
    1. Canonical words within a line that have gaps > *max_canonical_gap*
       are clipped to the first contiguous cluster.
    2. Ad-libs are only included if within *adlib_proximity* seconds
       of a canonical word (prevents chorus repeats from flooding segments).
    """
    if not merged_words:
        return []

    if not canonical_lines:
        # Fallback: single segment with all words
        return [{
            "start": merged_words[0]["start"],
            "end": merged_words[-1]["end"],
            "text": " ".join(w["text"] for w in merged_words),
            "words": merged_words,
        }]

    # Separate canonical and ad-lib words (preserving order)
    canonical_words = [w for w in merged_words if w.get("source") == "canonical"]
    adlib_words = [w for w in merged_words if w.get("source") == "ad-lib"]

    # Count expected words per line from canonical lyrics
    line_word_counts = []
    for line in canonical_lines:
        words_in_line = line.split()
        line_word_counts.append(len(words_in_line))

    # Assign canonical words to lines
    segments = []
    word_idx = 0
    for li, line in enumerate(canonical_lines):
        n_words = line_word_counts[li]
        line_words = canonical_words[word_idx:word_idx + n_words]
        word_idx += n_words

        if not line_words:
            continue

        # Clip to first contiguous cluster if words are spread too far
        # Pass ad-libs so gaps bridged by non-lyric vocals are preserved
        line_words = _cluster_canonical_words(
            line_words, max_canonical_gap, adlib_words=adlib_words,
        )

        # Only include ad-libs near the retained canonical words
        nearby = _nearby_adlibs(adlib_words, line_words, adlib_proximity)

        seg_words = list(line_words) + nearby
        seg_words.sort(key=lambda w: w["start"])

        segments.append({
            "start": seg_words[0]["start"],
            "end": seg_words[-1]["end"],
            "text": line,
            "words": seg_words,
        })

    # Enforce non-overlapping: clip each segment to end before the next starts
    for i in range(len(segments) - 1):
        if segments[i]["end"] > segments[i + 1]["start"]:
            segments[i]["end"] = segments[i + 1]["start"]
            # Also trim words that fall outside the clipped range
            segments[i]["words"] = [
                w for w in segments[i]["words"]
                if w["start"] < segments[i]["end"]
            ]

    # Distribute 0-duration segments crammed at end of track.
    # These are lyrics stable-ts couldn't align (e.g. repeated chorus at end).
    # Spread them into the gap between last valid segment and the stale point.
    _distribute_stale_tail_segments(segments)

    # Timestamp repair: re-interpolate words within segments that have
    # unreasonable internal timing (big gaps or crushed durations)
    for seg in segments:
        _repair_segment_word_timing(seg)

    return segments


def _build_segments_from_merged(
    merged_words: list[dict[str, Any]],
    max_gap: float = 2.0,
) -> list[dict[str, Any]]:
    """Group merged words into segments based on time gaps (fallback)."""
    if not merged_words:
        return []

    segments = []
    current_words = [merged_words[0]]

    for w in merged_words[1:]:
        prev_end = current_words[-1]["end"]
        if w["start"] - prev_end > max_gap:
            seg_text = " ".join(cw["text"] for cw in current_words)
            segments.append({
                "start": current_words[0]["start"],
                "end": current_words[-1]["end"],
                "text": seg_text,
                "words": current_words,
            })
            current_words = [w]
        else:
            current_words.append(w)

    if current_words:
        seg_text = " ".join(cw["text"] for cw in current_words)
        segments.append({
            "start": current_words[0]["start"],
            "end": current_words[-1]["end"],
            "text": seg_text,
            "words": current_words,
        })

    return segments


def align_track_two_pass(
    model: Any,
    audio_path: str | Path,
    canonical_lyrics: str,
    track_id: str,
    config: AlignmentConfig,
) -> list[dict[str, Any]]:
    """Two-pass alignment: force-align canonical + transcribe for ad-libs.

    Returns list of segments with merged words (canonical + ad-libs).
    """
    audio_str = str(audio_path)
    use_demucs = True

    # ── Pass 1: Force-align canonical lyrics ──
    logger.info("%s: Pass 1 — Force-aligning canonical lyrics with Demucs...", track_id)
    try:
        aligned = model.align(
            audio_str,
            canonical_lyrics,
            language=config.language,
            denoiser="demucs" if use_demucs else None,
            vad=True,
            suppress_silence=True,
        )
        # Refine timestamps for sub-word precision (non-critical)
        logger.info("%s: Refining word timestamps...", track_id)
        try:
            model.refine(audio_str, aligned, precision=0.05)
        except Exception as refine_err:
            logger.warning("%s: Refine failed (non-critical): %s", track_id, refine_err)
        aligned_words = _extract_words_from_result(aligned)
        logger.info("%s: Aligned %d canonical words", track_id, len(aligned_words))
    except Exception as e:
        logger.warning("%s: Force alignment failed: %s. Falling back to transcription only.", track_id, e)
        aligned_words = []

    # ── Pass 2: Free transcription to discover ad-libs ──
    logger.info("%s: Pass 2 — Free transcription for ad-libs...", track_id)
    try:
        transcribed = model.transcribe(
            audio_str,
            denoiser="demucs" if use_demucs else None,
            vad=True,
            suppress_silence=True,
            word_timestamps=True,
            condition_on_previous_text=config.condition_on_previous_text,
            compression_ratio_threshold=config.compression_ratio_threshold,
            no_speech_threshold=0.3,
            initial_prompt=f"Song lyrics: {canonical_lyrics[:300]}",
        )
        transcribed_words = _extract_words_from_result(transcribed)
        logger.info("%s: Transcribed %d words", track_id, len(transcribed_words))
    except Exception as e:
        logger.warning("%s: Free transcription failed: %s", track_id, e)
        transcribed_words = []

    # ── Rescue failed alignments using transcription timestamps ──
    if aligned_words and transcribed_words:
        aligned_words = _rescue_failed_words(aligned_words, transcribed_words)

    # ── Pass 3: Merge ──
    logger.info("%s: Merging aligned + transcribed...", track_id)
    merged_words = _merge_aligned_and_transcribed(aligned_words, transcribed_words)

    canonical_count = sum(1 for w in merged_words if w.get("source") == "canonical")
    adlib_count = sum(1 for w in merged_words if w.get("source") == "ad-lib")
    logger.info(
        "%s: Merged result: %d words (%d canonical, %d ad-libs)",
        track_id, len(merged_words), canonical_count, adlib_count,
    )

    # Build one segment per canonical line (critical for timeline matching)
    canonical_lines = [l for l in canonical_lyrics.split("\n") if l.strip()]
    segments = _build_segments_per_line(merged_words, canonical_lines)
    return segments


def transcribe_only(
    model: Any,
    audio_path: str | Path,
    track_id: str,
    config: AlignmentConfig,
    initial_prompt: str | None = None,
) -> list[dict[str, Any]]:
    """Single-pass transcription (for raw catalog alignment without canonical lyrics)."""
    audio_str = str(audio_path)

    logger.info("%s: Transcribing (single-pass)...", track_id)
    kwargs: dict[str, Any] = {
        "vad": True,
        "suppress_silence": True,
        "word_timestamps": True,
        "condition_on_previous_text": config.condition_on_previous_text,
        "compression_ratio_threshold": config.compression_ratio_threshold,
        "no_speech_threshold": 0.3,
    }
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt

    result = model.transcribe(audio_str, **kwargs)
    segments = _extract_segments_from_result(result)
    logger.info("%s: Transcribed %d segments", track_id, len(segments))
    return segments


def transcribe_and_align(
    audio_path: str | Path,
    output_path: str | Path,
    track_id: str,
    config: AlignmentConfig,
    *,
    model: Any = None,
    canonical_lyrics: str | None = None,
) -> AlignmentResult:
    """Align a single track. Uses two-pass if canonical lyrics provided.

    If *model* is not provided, loads a new model (slow — prefer passing one).
    """
    output_path = Path(output_path)

    if model is None:
        model = _load_model(config)

    if canonical_lyrics:
        segments = align_track_two_pass(
            model, audio_path, canonical_lyrics, track_id, config,
        )
        # Two-pass uses canonical text as ground truth — no hallucination filter.
        # The words ARE the canonical lyrics, filtering would destroy them.
    else:
        segments = transcribe_only(model, audio_path, track_id, config)
        # Only filter raw transcriptions (no canonical guidance).
        hall_cfg = config.hallucination
        segments = filter_segments(
            segments,
            filler=hall_cfg.filler_tokens if hall_cfg.filler_tokens else None,
            min_filler_repeat=hall_cfg.min_filler_repeat,
            min_any_repeat=hall_cfg.min_any_repeat,
            min_total_for_all_filler=hall_cfg.min_total_for_all_filler,
            min_filler_count=hall_cfg.min_filler_count,
            max_single_token_repeat=hall_cfg.max_single_token_repeat,
        )

    data = {"id": track_id, "segments": segments}

    ensure_dir(output_path.parent)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    logger.info("Alignment complete: %s (%d segments)", output_path, len(segments))
    return AlignmentResult.model_validate(data)


def assess_alignment_confidence(
    alignment: AlignmentResult,
    canonical_lines: list[str],
) -> str:
    """Check how well the alignment matches canonical lyrics.

    Returns "normal" or "low". Music tracks where Whisper invents
    fake lyrics will show very low overlap.
    """
    if not alignment.segments or not canonical_lines:
        return "low"

    all_align_tokens = []
    for seg in alignment.segments:
        all_align_tokens.extend(normalize(seg.text))

    all_canon_tokens = []
    for line in canonical_lines:
        all_canon_tokens.extend(normalize(line))

    if not all_align_tokens or not all_canon_tokens:
        return "low"

    overlap = token_overlap(all_align_tokens, all_canon_tokens)
    if overlap < 0.05:
        logger.warning(
            "Alignment confidence LOW (overlap=%.3f) — Whisper transcription "
            "has almost no overlap with canonical lyrics.",
            overlap,
        )
        return "low"

    return "normal"


def align_album_tracks(
    album_dir: Path,
    config: PipelineConfig,
    *,
    track_id: str | None = None,
) -> list[AlignmentResult]:
    """Align all (or one) MP3 tracks in an album directory.

    Uses two-pass strategy with canonical lyrics from the semantic matrix.
    Writes alignment JSON to ``albums/alignment/track_XX_words.json``.
    """
    if not check_dependencies():
        raise RuntimeError("Missing alignment dependencies (ffmpeg, stable-ts)")

    alignment_dir = album_dir.parent / "alignment"
    ensure_dir(alignment_dir)

    mp3_files = sorted(
        f for f in os.listdir(album_dir)
        if f.lower().endswith(".mp3")
    )
    if not mp3_files:
        raise FileNotFoundError(f"No .mp3 files found in {album_dir}")

    # Load model ONCE for all tracks
    model = _load_model(config.alignment)

    results = []

    if track_id:
        # Align single track
        try:
            track_num = int(track_id.split("_")[1])
        except (IndexError, ValueError) as exc:
            raise ValueError(f"Invalid track_id format: {track_id}") from exc

        if not (1 <= track_num <= len(mp3_files)):
            raise ValueError(
                f"track_id {track_id} out of range (found {len(mp3_files)} mp3s)"
            )

        mp3_file = mp3_files[track_num - 1]
        audio_path = album_dir / mp3_file
        out_path = alignment_dir / f"{track_id}_words.json"

        # Get canonical lyrics
        canonical = _get_canonical_lyrics(config.project_root, track_id)
        if canonical:
            logger.info("%s: Using canonical lyrics for guided alignment", track_id)

        result = transcribe_and_align(
            audio_path, out_path, track_id, config.alignment,
            model=model, canonical_lyrics=canonical,
        )
        results.append(result)
    else:
        # Align all tracks
        for idx, mp3_file in enumerate(mp3_files):
            tid = f"track_{idx + 1:02d}"
            audio_path = album_dir / mp3_file
            out_path = alignment_dir / f"{tid}_words.json"

            # Get canonical lyrics for this track
            canonical = _get_canonical_lyrics(config.project_root, tid)
            if canonical:
                logger.info("%s: Using canonical lyrics for guided alignment (%s)", tid, mp3_file)
            else:
                logger.info("%s: No canonical lyrics — transcription only (%s)", tid, mp3_file)

            result = transcribe_and_align(
                audio_path, out_path, tid, config.alignment,
                model=model, canonical_lyrics=canonical,
            )
            results.append(result)

    logger.info("Alignment run complete: %d tracks aligned", len(results))
    return results


def align_raw_catalog(
    choicekit_dir: Path,
    config: PipelineConfig,
    *,
    limit: int = 0,
    force: bool = False,
) -> int:
    """Align all RAW MP3s in a Choice Kit for catalog classification.

    Uses single-pass transcription (no canonical lyrics for raw files).
    """
    if not check_dependencies():
        raise RuntimeError("Missing alignment dependencies (ffmpeg, stable-ts)")

    index_path = choicekit_dir / "RAW_index.json"
    if not index_path.exists():
        raise FileNotFoundError(
            f"RAW_index.json not found at {index_path}. "
            "Run 'chak catalog extract' first."
        )

    raw_index = load_json(index_path)
    if not isinstance(raw_index, list):
        raise ValueError("RAW_index.json must be a JSON array")

    raw_alignment_dir = choicekit_dir / "RAW" / "alignment"
    ensure_dir(raw_alignment_dir)

    # Load model once
    model = _load_model(config.alignment)

    repo_root = choicekit_dir.parent
    processed = 0

    for item in raw_index:
        rel = item.get("raw_path")
        name = item.get("name")
        if not rel or not name:
            continue

        audio_path = repo_root / rel.replace("/", os.sep)
        if not audio_path.exists():
            logger.warning("RAW MP3 missing: %s", audio_path)
            continue

        stem = audio_path.stem
        out_path = raw_alignment_dir / f"{stem}_words.json"

        if out_path.exists() and not force:
            continue

        logger.info("Aligning RAW %s -> %s", name, out_path.name)
        transcribe_and_align(
            audio_path, out_path, stem, config.alignment,
            model=model,
        )
        processed += 1

        if limit and processed >= limit:
            logger.info("Hit limit=%d, stopping.", limit)
            break

    logger.info("RAW alignment complete: %d file(s) aligned.", processed)
    return processed
