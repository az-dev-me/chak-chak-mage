"""Whisper hallucination detection.

Single source of truth — replaces divergent implementations in
auto_aligner.py (thresholds: 2/5/8/25) and validate_album_alignments.py
(thresholds: 3/5/10/20). Now uses configurable thresholds from chak_pipeline.toml.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


# Default filler tokens (used if config is not available).
DEFAULT_FILLER: frozenset[str] = frozenset({
    "oh", "ooh", "oooh", "oh,", "ooh,",
    "ah", "aah", "ah,",
    "uh", "huh",
    "the", "la", "na",
    "yeah", "yea", "yo", "hey",
    "mm", "mmm",
    "music",
})

# Default thresholds matching the auto_aligner.py canonical values.
DEFAULT_MIN_FILLER_REPEAT = 2
DEFAULT_MIN_ANY_REPEAT = 8
DEFAULT_MIN_TOTAL_FOR_ALL_FILLER = 3
DEFAULT_MIN_FILLER_COUNT = 5
DEFAULT_MAX_SINGLE_TOKEN_REPEAT = 25


def is_hallucinated(
    segment: dict[str, Any],
    *,
    filler: frozenset[str] | None = None,
    min_filler_repeat: int = DEFAULT_MIN_FILLER_REPEAT,
    min_any_repeat: int = DEFAULT_MIN_ANY_REPEAT,
    min_total_for_all_filler: int = DEFAULT_MIN_TOTAL_FOR_ALL_FILLER,
    min_filler_count: int = DEFAULT_MIN_FILLER_COUNT,
    max_single_token_repeat: int = DEFAULT_MAX_SINGLE_TOKEN_REPEAT,
) -> bool:
    """Return True if this segment is likely Whisper hallucination.

    Checks for repetitive filler patterns that Whisper invents when it
    hears non-speech audio (instrumentals, noise).
    """
    filler_set = filler if filler is not None else DEFAULT_FILLER

    words = segment.get("words", [])
    if not words:
        return True

    tokens = [
        w.get("text", "").strip().lower().rstrip(",")
        for w in words
        if w.get("text")
    ]
    if not tokens:
        return True

    unique = set(tokens)

    # Single token repeated → hallucination if filler or very long
    if len(unique) == 1:
        if tokens[0] in filler_set and len(tokens) >= min_filler_repeat:
            return True
        return len(tokens) > max_single_token_repeat

    # Two or fewer unique tokens, all filler, above threshold
    if len(unique) <= 2 and len(tokens) >= min_total_for_all_filler:
        if all(t in filler_set for t in unique):
            return True

    # Any specific filler repeated too many times
    c = Counter(tokens)
    for t, n in c.items():
        if t in filler_set and n >= min_filler_count:
            return True
        if n >= min_any_repeat:
            return True

    return False


def filter_segments(
    segments: list[dict[str, Any]],
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Remove hallucinated segments, keeping only real content.

    Passes all keyword args through to ``is_hallucinated()``.
    """
    if not segments:
        return segments
    return [
        {
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"],
            "words": seg["words"],
        }
        for seg in segments
        if not is_hallucinated(seg, **kwargs)
    ]
