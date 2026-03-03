"""Text normalization utilities.

Single source of truth — replaces 4 duplicate normalize() implementations
across build_timelines.py, build_catalog_timelines.py, raw_catalog_classify.py,
and build_album_timeline.js.
"""

from __future__ import annotations

import re

# Stopwords used by classification and enhanced matching.
# Vocal fillers / adlibs that destroy similarity are included.
STOPWORDS: frozenset[str] = frozenset({
    # Common function words
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "so",
    "to", "of", "in", "on", "at", "by", "for", "with", "as",
    "is", "are", "was", "were", "be", "been", "being", "am",
    "i", "you", "he", "she", "it", "we", "they", "me", "my", "your",
    "our", "their", "him", "her", "them",
    "this", "that", "these", "those", "there", "here",
    "from", "into", "out", "up", "down", "over", "under",
    "again", "once", "all", "any", "some", "no", "not",
    "only", "very", "just", "now", "too",
    # Vocal fillers / adlibs
    "oh", "ooh", "oooh", "ah", "aah", "aaah", "uh", "huh",
    "mm", "mmm", "la", "na", "yeah", "yea", "yo", "hey", "woo", "whoa",
})

_CLEAN_RE = re.compile(r"[^a-z0-9\s]+")
_CLEAN_KEEP_APOSTROPHE_RE = re.compile(r"[^a-z0-9\s']")


def normalize(text: str) -> list[str]:
    """Lowercase, strip non-alphanumeric, split into tokens.

    This is the base normalization used by timeline matching and fusion.
    Matches the original regex ``re.sub(r"[^a-z0-9\\s]+", " ", text.lower())``.
    """
    if not text:
        return []
    cleaned = _CLEAN_RE.sub(" ", text.lower())
    return [t for t in cleaned.split() if t]


def norm_tokens(text: str, *, stopwords: frozenset[str] | None = None) -> list[str]:
    """Normalize *with* stopword removal and minimum-length filtering.

    Used by classification (TF-IDF) where common words hurt accuracy.
    """
    if not text:
        return []
    sw = stopwords if stopwords is not None else STOPWORDS
    cleaned = _CLEAN_KEEP_APOSTROPHE_RE.sub(" ", text.lower())
    return [t for t in cleaned.split() if t and t not in sw and len(t) > 1]
