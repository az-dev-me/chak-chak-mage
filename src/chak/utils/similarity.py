"""Similarity scoring functions.

Single source of truth — replaces 4 duplicate similarity() implementations
and consolidates cosine_tfidf and jaccard from other scripts.
"""

from __future__ import annotations

import math
from collections import Counter


def token_overlap(seg_tokens: list[str], line_tokens: list[str]) -> float:
    """Compute set-overlap similarity: |intersection| / |line_tokens|.

    Returns 0.0 if either input is empty.
    This is the primary metric used by timeline matching and fusion.
    """
    if not seg_tokens or not line_tokens:
        return 0.0
    overlap = len(set(seg_tokens) & set(line_tokens))
    return overlap / len(line_tokens)


def jaccard(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Jaccard similarity: |intersection| / |union|.

    Used by archive catalog builder for track assignment.
    """
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def cosine_tfidf(
    doc_tokens: list[str],
    ref_tokens: list[str],
    idf: dict[str, float],
) -> float:
    """Cosine similarity weighted by IDF scores.

    Used by raw catalog classification for track assignment.

    Parameters
    ----------
    doc_tokens:
        Tokens from the document being scored (e.g. Whisper transcript).
    ref_tokens:
        Tokens from the reference (e.g. canonical lyrics for a track).
    idf:
        Pre-computed IDF mapping (token -> IDF weight).
    """
    if not doc_tokens or not ref_tokens:
        return 0.0

    tf_doc = Counter(doc_tokens)
    tf_ref = Counter(ref_tokens)

    # Build TF-IDF vectors over the union of terms
    all_terms = set(tf_doc) | set(tf_ref)
    dot = 0.0
    mag_doc = 0.0
    mag_ref = 0.0

    for term in all_terms:
        w = idf.get(term, 0.0)
        d = tf_doc.get(term, 0) * w
        r = tf_ref.get(term, 0) * w
        dot += d * r
        mag_doc += d * d
        mag_ref += r * r

    denom = math.sqrt(mag_doc) * math.sqrt(mag_ref)
    return dot / denom if denom > 0 else 0.0


def build_idf(documents: list[list[str]]) -> dict[str, float]:
    """Build an IDF table from a list of tokenized documents.

    IDF(t) = log(N / df(t)) where df(t) = number of documents containing t.
    """
    n = len(documents)
    if n == 0:
        return {}

    df: Counter[str] = Counter()
    for doc in documents:
        df.update(set(doc))

    return {term: math.log(n / count) for term, count in df.items() if count > 0}
