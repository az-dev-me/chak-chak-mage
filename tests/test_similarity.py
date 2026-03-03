"""Tests for chak.utils.similarity — scoring functions."""

import math

import pytest
from chak.utils.similarity import build_idf, cosine_tfidf, jaccard, token_overlap


class TestTokenOverlap:
    def test_exact_match(self):
        assert token_overlap(["fire", "run"], ["fire", "run"]) == 1.0

    def test_partial_overlap(self):
        # 1 of 2 line tokens matched
        assert token_overlap(["fire", "night"], ["fire", "run"]) == 0.5

    def test_no_overlap(self):
        assert token_overlap(["hello"], ["world"]) == 0.0

    def test_empty_seg(self):
        assert token_overlap([], ["fire"]) == 0.0

    def test_empty_line(self):
        assert token_overlap(["fire"], []) == 0.0

    def test_both_empty(self):
        assert token_overlap([], []) == 0.0

    def test_superset_seg(self):
        # seg has more tokens than line — overlap is 100%
        assert token_overlap(["fire", "run", "night", "glow"], ["fire", "run"]) == 1.0

    def test_subset_seg(self):
        # seg has fewer tokens than line
        result = token_overlap(["fire"], ["fire", "run", "night"])
        assert abs(result - 1 / 3) < 0.01

    def test_duplicate_tokens_are_set_based(self):
        # Duplicates don't increase the overlap
        assert token_overlap(["fire", "fire", "fire"], ["fire", "run"]) == 0.5


class TestJaccard:
    def test_identical(self):
        assert jaccard(["a", "b"], ["a", "b"]) == 1.0

    def test_no_overlap(self):
        assert jaccard(["a"], ["b"]) == 0.0

    def test_partial(self):
        # intersection=1, union=3
        result = jaccard(["a", "b"], ["b", "c"])
        assert abs(result - 1 / 3) < 0.01

    def test_empty(self):
        assert jaccard([], ["a"]) == 0.0
        assert jaccard(["a"], []) == 0.0
        assert jaccard([], []) == 0.0


class TestBuildIdf:
    def test_single_doc(self):
        idf = build_idf([["hello", "world"]])
        # IDF = log(1/1) = 0 for both
        assert idf["hello"] == 0.0
        assert idf["world"] == 0.0

    def test_two_docs_exclusive(self):
        idf = build_idf([["hello"], ["world"]])
        # Each appears in 1 of 2 docs: log(2/1) = log(2)
        assert abs(idf["hello"] - math.log(2)) < 0.001
        assert abs(idf["world"] - math.log(2)) < 0.001

    def test_common_term_lower_idf(self):
        idf = build_idf([["a", "x"], ["a", "y"], ["a", "z"]])
        # "a" in all 3 docs: log(3/3) = 0
        # others in 1: log(3/1) = log(3)
        assert idf["a"] == 0.0
        assert abs(idf["x"] - math.log(3)) < 0.001

    def test_empty_documents(self):
        assert build_idf([]) == {}


class TestCosineTfidf:
    def test_identical_docs(self):
        idf = build_idf([["fire", "run"], ["fire", "night"]])
        score = cosine_tfidf(["fire", "run"], ["fire", "run"], idf)
        assert abs(score - 1.0) < 0.01

    def test_no_overlap(self):
        idf = build_idf([["a"], ["b"]])
        assert cosine_tfidf(["a"], ["b"], idf) == 0.0

    def test_empty_doc(self):
        assert cosine_tfidf([], ["fire"], {}) == 0.0

    def test_empty_ref(self):
        assert cosine_tfidf(["fire"], [], {}) == 0.0
