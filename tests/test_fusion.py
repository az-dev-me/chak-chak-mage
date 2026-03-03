"""Tests for chak.stages.fuse — data fusion functions."""

import pytest
from chak.stages.fuse import (
    build_media_array,
    build_semantic_index,
    best_semantic_for_lyric,
    flatten_words,
    words_for_range,
    synthesize_words_from_lyric,
    _find_closest_concept,
)


class TestBuildSemanticIndex:
    def test_basic(self):
        matrix = {
            "track_01": {
                "lines": [
                    {"lyric": "fire burns bright", "real_meaning": "passion", "media_queries": ["fire"]},
                    {"lyric": "night falls slowly", "real_meaning": "rest", "media_queries": ["night"]},
                ]
            }
        }
        index = build_semantic_index(matrix)
        assert len(index) == 2
        assert index[0]["track_id"] == "track_01"
        assert index[0]["lyric"] == "fire burns bright"
        assert len(index[0]["tokens"]) == 3

    def test_multiple_tracks(self):
        matrix = {
            "track_01": {"lines": [{"lyric": "hello"}]},
            "track_02": {"lines": [{"lyric": "world"}]},
        }
        index = build_semantic_index(matrix)
        assert len(index) == 2
        assert index[0]["track_id"] == "track_01"
        assert index[1]["track_id"] == "track_02"

    def test_empty_matrix(self):
        assert build_semantic_index({}) == []


class TestBestSemanticForLyric:
    def test_exact_match(self):
        index = [
            {"lyric": "fire burns bright", "tokens": ["fire", "burns", "bright"],
             "semantic_line": {"real_meaning": "passion"}},
        ]
        result = best_semantic_for_lyric(index, "fire burns bright")
        assert result is not None
        assert result["semantic_line"]["real_meaning"] == "passion"

    def test_partial_match_above_threshold(self):
        index = [
            {"lyric": "fire burns bright", "tokens": ["fire", "burns", "bright"],
             "semantic_line": {"real_meaning": "passion"}},
        ]
        result = best_semantic_for_lyric(index, "fire burns in the dark", min_sim=0.3)
        assert result is not None

    def test_no_match_below_threshold(self):
        index = [
            {"lyric": "fire burns bright", "tokens": ["fire", "burns", "bright"],
             "semantic_line": {"real_meaning": "passion"}},
        ]
        result = best_semantic_for_lyric(index, "water flows gently", min_sim=0.45)
        assert result is None

    def test_empty_index(self):
        assert best_semantic_for_lyric([], "hello") is None

    def test_empty_lyric(self):
        index = [
            {"lyric": "hello", "tokens": ["hello"],
             "semantic_line": {"real_meaning": "greeting"}},
        ]
        assert best_semantic_for_lyric(index, "") is None


class TestFlattenWords:
    def test_basic(self):
        alignment = {
            "segments": [
                {"text": "hello world", "words": [
                    {"start": 0.0, "end": 0.5, "text": "hello"},
                    {"start": 0.5, "end": 1.0, "text": "world"},
                ]},
            ]
        }
        result = flatten_words(alignment)
        assert len(result) == 2
        assert result[0]["text"] == "hello"
        assert result[1]["text"] == "world"

    def test_multiple_segments(self):
        alignment = {
            "segments": [
                {"text": "a", "words": [{"start": 0.0, "end": 0.5, "text": "a"}]},
                {"text": "b", "words": [{"start": 1.0, "end": 1.5, "text": "b"}]},
            ]
        }
        result = flatten_words(alignment)
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[1]["start"] == 1.0

    def test_sorted_by_start(self):
        alignment = {
            "segments": [
                {"text": "b", "words": [{"start": 1.0, "end": 1.5, "text": "b"}]},
                {"text": "a", "words": [{"start": 0.0, "end": 0.5, "text": "a"}]},
            ]
        }
        result = flatten_words(alignment)
        assert result[0]["text"] == "a"
        assert result[1]["text"] == "b"

    def test_empty_alignment(self):
        assert flatten_words({"segments": []}) == []
        assert flatten_words({}) == []


class TestWordsForRange:
    def test_basic(self):
        words = [
            {"start": 0.0, "end": 0.5, "text": "a"},
            {"start": 1.0, "end": 1.5, "text": "b"},
            {"start": 2.0, "end": 2.5, "text": "c"},
        ]
        result = words_for_range(words, 0.9, 1.6)
        assert len(result) == 1
        assert result[0]["text"] == "b"

    def test_full_range(self):
        words = [
            {"start": 0.0, "end": 0.5, "text": "a"},
            {"start": 1.0, "end": 1.5, "text": "b"},
        ]
        result = words_for_range(words, 0.0, 2.0)
        assert len(result) == 2

    def test_empty_range(self):
        words = [
            {"start": 5.0, "end": 5.5, "text": "a"},
        ]
        result = words_for_range(words, 0.0, 1.0)
        assert len(result) == 0


class TestSynthesizeWordsFromLyric:
    def test_basic(self):
        result = synthesize_words_from_lyric("hello world", 0.0, 2.0)
        assert len(result) == 2
        assert result[0].text == "hello"
        assert result[1].text == "world"
        assert result[0].start == 0.0
        assert result[0].end == 1.0
        assert result[1].start == 1.0
        assert result[1].end == 2.0

    def test_single_word(self):
        result = synthesize_words_from_lyric("Nothing.", 5.0, 10.0)
        assert len(result) == 1
        assert result[0].text == "Nothing."
        assert result[0].start == 5.0
        assert result[0].end == 10.0

    def test_empty_lyric(self):
        assert synthesize_words_from_lyric("", 0.0, 5.0) == []
        assert synthesize_words_from_lyric("   ", 0.0, 5.0) == []

    def test_even_distribution(self):
        result = synthesize_words_from_lyric("a b c d", 0.0, 4.0)
        assert len(result) == 4
        for i, w in enumerate(result):
            assert w.start == float(i)
            assert w.end == float(i + 1)


class TestBuildMediaArray:
    def test_with_manifest(self):
        manifest = {
            "concepts": {
                "fire image": {"filename": "fire.jpg", "status": "ok"},
            }
        }
        result = build_media_array(["fire image"], 0.0, 5.0, manifest)
        assert len(result) == 1
        assert result[0].url == "media/fire.jpg"
        assert result[0].offset == 0.0

    def test_multiple_queries_distributed(self):
        manifest = {
            "concepts": {
                "a": {"filename": "a.jpg", "status": "ok"},
                "b": {"filename": "b.jpg", "status": "ok"},
            }
        }
        result = build_media_array(["a", "b"], 0.0, 10.0, manifest)
        assert len(result) == 2
        assert result[0].offset == 0.0
        assert result[1].offset == 5.0

    def test_missing_concept_skipped(self):
        # Concept exists in manifest but is failed — no ok fallback either
        manifest = {"concepts": {
            "something else": {"filename": "other.jpg", "status": "failed"},
        }}
        result = build_media_array(["nonexistent"], 0.0, 5.0, manifest)
        assert len(result) == 0

    def test_no_manifest(self):
        result = build_media_array(["test"], 0.0, 5.0, None)
        assert len(result) == 1
        assert "placeholder" in result[0].url

    def test_empty_queries(self):
        result = build_media_array([], 0.0, 5.0, {})
        assert result == []


class TestFindClosestConcept:
    def test_finds_similar(self):
        concepts = {
            "a magical forest glow": {"filename": "forest.jpg", "status": "ok"},
            "dark night sky": {"filename": "night.jpg", "status": "ok"},
        }
        result = _find_closest_concept("magical forest", concepts)
        assert result is not None
        assert result["meta"]["filename"] == "forest.jpg"

    def test_ignores_failed_concepts(self):
        concepts = {
            "fire burns": {"filename": "fire.jpg", "status": "failed"},
        }
        result = _find_closest_concept("fire burns bright", concepts)
        assert result is None

    def test_no_overlap_returns_none(self):
        concepts = {
            "xyz abc def": {"filename": "xyz.jpg", "status": "ok"},
        }
        result = _find_closest_concept("fire burns", concepts)
        assert result is None
