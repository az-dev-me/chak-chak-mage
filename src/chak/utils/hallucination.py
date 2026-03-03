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
    kept = []
    for seg in segments:
        if is_hallucinated(seg, **kwargs):
            continue
        # Preserve all fields (including 'source' on words if present)
        out = {
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"],
            "words": seg.get("words", []),
        }
        kept.append(out)
    return kept


def filter_word_hallucinations(
    words: list[dict[str, Any]],
    canonical_words_set: frozenset[str] | None = None,
    *,
    min_consecutive_repeat: int = 3,
) -> list[dict[str, Any]]:
    """Smart word-level hallucination filter.

    Only removes words that:
    1. Don't fuzzy-match ANY canonical word, AND
    2. Appear consecutively repeated min_consecutive_repeat+ times

    Single occurrences of non-canonical words are kept (ad-libs).
    Canonical-matching words are always kept.

    Parameters
    ----------
    words:
        List of word dicts with at least 'text' key.
    canonical_words_set:
        Normalized canonical words for comparison. If None, no
        canonical filtering is applied (only consecutive repeats).
    min_consecutive_repeat:
        Minimum consecutive repetitions of the same non-canonical
        word to consider it hallucination.
    """
    if not words:
        return words

    canon = canonical_words_set or frozenset()

    # Detect consecutive repetitions
    # Group words into runs of identical normalized text
    runs: list[list[int]] = []
    current_run: list[int] = [0]
    for i in range(1, len(words)):
        prev_norm = words[i - 1].get("text", "").strip().lower().rstrip(".,!?")
        curr_norm = words[i].get("text", "").strip().lower().rstrip(".,!?")
        if curr_norm == prev_norm:
            current_run.append(i)
        else:
            runs.append(current_run)
            current_run = [i]
    runs.append(current_run)

    # Identify indices to remove
    remove_indices: set[int] = set()
    for run in runs:
        if len(run) < min_consecutive_repeat:
            continue
        # Check if this repeated word matches any canonical word
        word_text = words[run[0]].get("text", "").strip().lower().rstrip(".,!?")
        if word_text in canon:
            continue  # Canonical word repeated — could be intentional (chorus)
        # Non-canonical word repeated consecutively → hallucination
        remove_indices.update(run)

    return [w for i, w in enumerate(words) if i not in remove_indices]
