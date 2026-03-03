"""Tests for chak.stages.timeline — timeline building with two-pass matching."""

import pytest
from chak.stages.timeline import _aggregate_and_rematch, _match_segments_to_lines


def _make_segment(text: str, start: float, end: float) -> dict:
    """Create a minimal alignment segment for testing."""
    words = [
        {"start": start + i * 0.3, "end": start + (i + 1) * 0.3, "text": w}
        for i, w in enumerate(text.split())
    ]
    return {"text": text, "words": words, "start": start, "end": end}


class TestMatchSegmentsToLines:
    def test_exact_match_single_line(self):
        segments = [_make_segment("fire burns bright", 0.0, 3.0)]
        canonical = ["fire burns bright"]
        result = _match_segments_to_lines(segments, canonical, 0.45)
        assert len(result) == 1
        assert result[0]["line_index"] == 0
        assert result[0]["lyric"] == "fire burns bright"

    def test_exact_match_multiple_lines(self):
        segments = [
            _make_segment("hello world", 0.0, 2.0),
            _make_segment("fire burns", 2.5, 4.0),
        ]
        canonical = ["hello world", "fire burns"]
        result = _match_segments_to_lines(segments, canonical, 0.45)
        assert len(result) == 2
        assert result[0]["line_index"] == 0
        assert result[1]["line_index"] == 1

    def test_unmatched_becomes_instrumental(self):
        segments = [_make_segment("xyz abc def", 0.0, 3.0)]
        canonical = ["fire burns bright"]
        result = _match_segments_to_lines(segments, canonical, 0.45)
        assert len(result) == 1
        assert result[0]["line_index"] is None
        assert "instrumental" in result[0]["id"]

    def test_partial_overlap_above_threshold(self):
        segments = [_make_segment("fire burns in the night", 0.0, 5.0)]
        canonical = ["fire burns bright"]
        # "fire" and "burns" overlap = 2/3 ≈ 0.67 > 0.45
        result = _match_segments_to_lines(segments, canonical, 0.45)
        assert result[0]["line_index"] == 0

    def test_partial_overlap_below_threshold(self):
        segments = [_make_segment("fire night sky stars moon", 0.0, 5.0)]
        canonical = ["fire burns bright"]
        # Only "fire" overlaps = 1/3 ≈ 0.33 < 0.45
        result = _match_segments_to_lines(segments, canonical, 0.45)
        assert result[0]["line_index"] is None

    def test_forward_only_matching(self):
        """Once a line is matched, earlier lines should not be matched again."""
        segments = [
            _make_segment("fire burns", 0.0, 2.0),
            _make_segment("night falls", 2.5, 4.0),
            _make_segment("fire burns", 4.5, 6.0),  # repeated lyric
        ]
        canonical = ["fire burns", "night falls"]
        result = _match_segments_to_lines(segments, canonical, 0.45)
        assert result[0]["line_index"] == 0
        assert result[1]["line_index"] == 1
        # The 3rd segment still matches line 0, but forward-only allows same index
        assert result[2]["line_index"] == 1 or result[2]["line_index"] is None

    def test_low_threshold_for_music(self):
        segments = [_make_segment("fire something", 0.0, 2.0)]
        canonical = ["fire burns bright tonight"]
        # "fire" = 1/4 = 0.25 — matches at 0.25 but not at 0.45
        result_low = _match_segments_to_lines(segments, canonical, 0.25)
        result_high = _match_segments_to_lines(segments, canonical, 0.45)
        assert result_low[0]["line_index"] == 0
        assert result_high[0]["line_index"] is None

    def test_empty_segments(self):
        result = _match_segments_to_lines([], ["hello"], 0.45)
        assert result == []

    def test_empty_canonical(self):
        segments = [_make_segment("hello world", 0.0, 2.0)]
        result = _match_segments_to_lines(segments, [], 0.45)
        assert len(result) == 1
        assert result[0]["line_index"] is None


class TestAggregateAndRematch:
    def test_combines_consecutive_unmatched(self):
        # Two unmatched segments whose combined text matches a canonical line
        timeline = [
            {"id": "instrumental_0", "line_index": None, "occurrence_index": 0,
             "start": 0.0, "end": 1.0, "lyric": "fire burns"},
            {"id": "instrumental_1", "line_index": None, "occurrence_index": 1,
             "start": 1.0, "end": 2.0, "lyric": "bright tonight"},
        ]
        canonical = ["fire burns bright tonight"]
        result = _aggregate_and_rematch(timeline, canonical, 0.45)
        assert len(result) == 1
        assert result[0]["line_index"] == 0

    def test_preserves_matched_entries(self):
        timeline = [
            {"id": "line_0_occ_0", "line_index": 0, "occurrence_index": 0,
             "start": 0.0, "end": 2.0, "lyric": "hello world"},
        ]
        canonical = ["hello world"]
        result = _aggregate_and_rematch(timeline, canonical, 0.45)
        assert len(result) == 1
        assert result[0]["line_index"] == 0

    def test_cannot_combine_still_unmatched(self):
        timeline = [
            {"id": "instrumental_0", "line_index": None, "occurrence_index": 0,
             "start": 0.0, "end": 1.0, "lyric": "xyz abc"},
            {"id": "instrumental_1", "line_index": None, "occurrence_index": 1,
             "start": 1.0, "end": 2.0, "lyric": "def ghi"},
        ]
        canonical = ["fire burns bright"]
        result = _aggregate_and_rematch(timeline, canonical, 0.45)
        # Should keep both unmatched
        assert len(result) == 2
        assert all(e["line_index"] is None for e in result)

    def test_mixed_matched_and_unmatched(self):
        timeline = [
            {"id": "line_0_occ_0", "line_index": 0, "occurrence_index": 0,
             "start": 0.0, "end": 2.0, "lyric": "hello"},
            {"id": "instrumental_0", "line_index": None, "occurrence_index": 0,
             "start": 2.0, "end": 3.0, "lyric": "fire"},
            {"id": "instrumental_1", "line_index": None, "occurrence_index": 1,
             "start": 3.0, "end": 4.0, "lyric": "burns"},
            {"id": "line_1_occ_0", "line_index": 1, "occurrence_index": 0,
             "start": 4.0, "end": 6.0, "lyric": "goodbye"},
        ]
        canonical = ["hello", "fire burns", "goodbye"]
        result = _aggregate_and_rematch(timeline, canonical, 0.45)
        assert result[0]["line_index"] == 0
        assert result[1]["line_index"] == 1  # combined "fire" + "burns" → "fire burns"
        assert result[2]["line_index"] == 1  # "goodbye" original match stays
