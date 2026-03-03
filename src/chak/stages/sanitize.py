"""Stage 2: Alignment sanitization and validation.

Merges sanitize_raw_alignments.py and validate_album_alignments.py
into a single module with consistent thresholds.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from chak.config import HallucinationConfig, PipelineConfig
from chak.utils.hallucination import filter_segments, is_hallucinated

logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    """Report from validating alignment files."""
    file_path: str
    total_segments: int
    hallucinated_indices: list[int] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return len(self.hallucinated_indices) == 0


def _hall_kwargs(hall_cfg: HallucinationConfig) -> dict:
    """Convert HallucinationConfig to keyword args for hallucination functions."""
    return {
        "filler": hall_cfg.filler_tokens if hall_cfg.filler_tokens else None,
        "min_filler_repeat": hall_cfg.min_filler_repeat,
        "min_any_repeat": hall_cfg.min_any_repeat,
        "min_total_for_all_filler": hall_cfg.min_total_for_all_filler,
        "min_filler_count": hall_cfg.min_filler_count,
        "max_single_token_repeat": hall_cfg.max_single_token_repeat,
    }


def validate_alignment(
    alignment_path: Path,
    config: PipelineConfig,
) -> ValidationReport:
    """Check a single alignment file for hallucinated segments (non-destructive)."""
    with open(alignment_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments", [])
    kwargs = _hall_kwargs(config.alignment.hallucination)

    bad_indices = [
        i for i, seg in enumerate(segments)
        if is_hallucinated(seg, **kwargs)
    ]

    return ValidationReport(
        file_path=str(alignment_path),
        total_segments=len(segments),
        hallucinated_indices=bad_indices,
    )


def sanitize_alignment(
    alignment_path: Path,
    config: PipelineConfig,
) -> ValidationReport:
    """Remove hallucinated segments from an alignment file (destructive)."""
    with open(alignment_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments", [])
    kwargs = _hall_kwargs(config.alignment.hallucination)

    bad_indices = [
        i for i, seg in enumerate(segments)
        if is_hallucinated(seg, **kwargs)
    ]

    if bad_indices:
        data["segments"] = filter_segments(segments, **kwargs)
        with open(alignment_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        logger.info(
            "Sanitized %s: removed %d hallucinated segments",
            alignment_path.name, len(bad_indices),
        )

    return ValidationReport(
        file_path=str(alignment_path),
        total_segments=len(segments),
        hallucinated_indices=bad_indices,
    )


def validate_album_alignments(
    album_dir: Path,
    config: PipelineConfig,
) -> list[ValidationReport]:
    """Validate all alignment files for an album."""
    alignment_dir = album_dir.parent / "alignment"
    if not alignment_dir.is_dir():
        logger.error("Alignment directory not found: %s", alignment_dir)
        return []

    reports = []
    for f in sorted(alignment_dir.iterdir()):
        if f.suffix == ".json" and f.stem.startswith("track_") and f.stem.endswith("_words"):
            report = validate_alignment(f, config)
            if report.is_clean:
                logger.info("%s: OK (%d segments)", f.name, report.total_segments)
            else:
                logger.warning(
                    "%s: %d hallucinated segment(s) at indices %s",
                    f.name, len(report.hallucinated_indices),
                    report.hallucinated_indices[:10],
                )
            reports.append(report)

    return reports


def sanitize_album_alignments(
    album_dir: Path,
    config: PipelineConfig,
) -> list[ValidationReport]:
    """Sanitize all alignment files for an album (remove hallucinated segments)."""
    alignment_dir = album_dir.parent / "alignment"
    if not alignment_dir.is_dir():
        logger.error("Alignment directory not found: %s", alignment_dir)
        return []

    reports = []
    for f in sorted(alignment_dir.iterdir()):
        if f.suffix == ".json" and f.stem.startswith("track_") and f.stem.endswith("_words"):
            report = sanitize_alignment(f, config)
            reports.append(report)

    return reports
