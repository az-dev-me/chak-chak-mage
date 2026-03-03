"""Stage 1: Audio alignment via Whisper.

Merges auto_aligner.py, catalog_aligner.py, raw_catalog_aligner.py,
and archive_aligner.py into a single module.
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
    """Verify Whisper and ffmpeg are available."""
    if shutil.which("ffmpeg") is None:
        logger.warning("ffmpeg is not installed or not in PATH.")
        return False
    try:
        import whisper  # noqa: F401
        import whisper_timestamped  # noqa: F401
    except ImportError:
        logger.warning(
            "OpenAI Whisper or whisper-timestamped not installed. "
            "Install with: pip install -U openai-whisper whisper-timestamped"
        )
        return False
    return True


def transcribe_and_align(
    audio_path: str | Path,
    output_path: str | Path,
    track_id: str,
    config: AlignmentConfig,
) -> AlignmentResult:
    """Run Whisper to produce word-level alignment for an audio file.

    Returns the validated AlignmentResult and writes it to *output_path*.
    """
    import whisper_timestamped as whisper

    audio_path = str(audio_path)
    output_path = Path(output_path)

    logger.info("Loading Whisper model '%s' on %s for %s",
                config.whisper_model, config.whisper_device, audio_path)
    model = whisper.load_model(config.whisper_model, device=config.whisper_device)

    logger.info("Transcribing and extracting word timestamps...")
    result = whisper.transcribe(
        model,
        audio_path,
        language=config.language,
        verbose=False,
        condition_on_previous_text=config.condition_on_previous_text,
        compression_ratio_threshold=config.compression_ratio_threshold,
    )

    segments_out = []
    for segment in result.get("segments", []):
        words_out = []
        for w in segment.get("words", []):
            start = w.get("start")
            end = w.get("end")
            text = w.get("text", "").strip()
            if start is None or end is None or not text:
                continue
            words_out.append({
                "start": round(float(start), 2),
                "end": round(float(end), 2),
                "text": text,
            })

        seg_start = segment.get("start")
        seg_end = segment.get("end")
        seg_text = segment.get("text", "").strip()
        if seg_start is None or seg_end is None or not seg_text:
            continue

        segments_out.append({
            "start": round(float(seg_start), 2),
            "end": round(float(seg_end), 2),
            "text": seg_text,
            "words": words_out,
        })

    # Filter out Whisper hallucination (repeated filler)
    hall_cfg = config.hallucination
    segments_out = filter_segments(
        segments_out,
        filler=hall_cfg.filler_tokens if hall_cfg.filler_tokens else None,
        min_filler_repeat=hall_cfg.min_filler_repeat,
        min_any_repeat=hall_cfg.min_any_repeat,
        min_total_for_all_filler=hall_cfg.min_total_for_all_filler,
        min_filler_count=hall_cfg.min_filler_count,
        max_single_token_repeat=hall_cfg.max_single_token_repeat,
    )

    data = {"id": track_id, "segments": segments_out}

    ensure_dir(output_path.parent)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    logger.info("Alignment complete: %s (%d segments)", output_path, len(segments_out))
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

    # Combine all alignment text
    all_align_tokens = []
    for seg in alignment.segments:
        all_align_tokens.extend(normalize(seg.text))

    # Combine all canonical lyrics
    all_canon_tokens = []
    for line in canonical_lines:
        all_canon_tokens.extend(normalize(line))

    if not all_align_tokens or not all_canon_tokens:
        return "low"

    overlap = token_overlap(all_align_tokens, all_canon_tokens)
    if overlap < 0.05:
        logger.warning(
            "Alignment confidence LOW (overlap=%.3f) — Whisper transcription "
            "has almost no overlap with canonical lyrics. This is likely a "
            "music-heavy track.",
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

    Writes alignment JSON to ``albums/alignment/track_XX_words.json``.
    """
    if not check_dependencies():
        raise RuntimeError("Missing alignment dependencies (ffmpeg, whisper)")

    alignment_dir = album_dir.parent / "alignment"
    ensure_dir(alignment_dir)

    mp3_files = sorted(
        f for f in os.listdir(album_dir)
        if f.lower().endswith(".mp3")
    )
    if not mp3_files:
        raise FileNotFoundError(f"No .mp3 files found in {album_dir}")

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
        result = transcribe_and_align(audio_path, out_path, track_id, config.alignment)
        results.append(result)
    else:
        # Align all tracks
        for idx, mp3_file in enumerate(mp3_files):
            tid = f"track_{idx + 1:02d}"
            audio_path = album_dir / mp3_file
            out_path = alignment_dir / f"{tid}_words.json"
            logger.info("Aligning %s -> %s", tid, mp3_file)
            result = transcribe_and_align(audio_path, out_path, tid, config.alignment)
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

    Reads RAW_index.json and writes alignment JSON to RAW/alignment/.

    Parameters
    ----------
    choicekit_dir:
        Path to the Choice Kit directory (contains RAW/ and RAW_index.json).
    config:
        Pipeline configuration.
    limit:
        Maximum number of files to align (0 = no limit).
    force:
        If True, re-align files that already have alignment data.

    Returns the number of files aligned.
    """
    if not check_dependencies():
        raise RuntimeError("Missing alignment dependencies (ffmpeg, whisper)")

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
        transcribe_and_align(audio_path, out_path, stem, config.alignment)
        processed += 1

        if limit and processed >= limit:
            logger.info("Hit limit=%d, stopping.", limit)
            break

    logger.info("RAW alignment complete: %d file(s) aligned.", processed)
    return processed
