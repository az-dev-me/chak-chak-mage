"""Tests for chak.utils.hallucination — Whisper hallucination detection."""

import pytest
from chak.utils.hallucination import (
    DEFAULT_FILLER,
    filter_segments,
    is_hallucinated,
)


def _seg(words_text: list[str]) -> dict:
    """Build a minimal segment dict from a list of word strings."""
    words = [
        {"start": float(i), "end": float(i + 0.5), "text": t}
        for i, t in enumerate(words_text)
    ]
    return {
        "start": 0.0,
        "end": float(len(words_text)),
        "text": " ".join(words_text),
        "words": words,
    }


class TestIsHallucinated:
    def test_single_filler_repeated(self):
        seg = _seg(["oh", "oh", "oh"])
        assert is_hallucinated(seg) is True

    def test_single_content_word_not_hallucinated(self):
        seg = _seg(["fire", "fire"])
        assert is_hallucinated(seg) is False

    def test_single_non_filler_many_repeats(self):
        # Exceeds max_single_token_repeat (default 25)
        seg = _seg(["fire"] * 30)
        assert is_hallucinated(seg) is True

    def test_two_fillers_mixed(self):
        seg = _seg(["oh", "ah", "oh", "ah"])
        assert is_hallucinated(seg) is True

    def test_real_content(self):
        seg = _seg(["the", "fire", "was", "always", "there"])
        assert is_hallucinated(seg) is False

    def test_no_words(self):
        seg = {"start": 0, "end": 1, "text": "hello", "words": []}
        assert is_hallucinated(seg) is True

    def test_filler_count_threshold(self):
        # "oh" repeated 5 times (min_filler_count default=5)
        seg = _seg(["the", "fire", "oh", "oh", "oh", "oh", "oh"])
        assert is_hallucinated(seg) is True

    def test_filler_below_threshold(self):
        # "oh" repeated 4 times (below min_filler_count=5)
        seg = _seg(["the", "fire", "run", "oh", "oh", "oh", "oh"])
        assert is_hallucinated(seg) is False

    def test_any_repeat_threshold(self):
        # Non-filler word repeated 8 times (min_any_repeat=8)
        seg = _seg(["fire"] * 8 + ["run"])
        assert is_hallucinated(seg) is True

    def test_custom_filler_set(self):
        seg = _seg(["custom", "custom", "custom"])
        assert is_hallucinated(seg, filler=frozenset({"custom"})) is True
        assert is_hallucinated(seg, filler=frozenset({"other"})) is False

    def test_custom_thresholds(self):
        seg = _seg(["oh", "oh"])
        assert is_hallucinated(seg, min_filler_repeat=3) is False
        assert is_hallucinated(seg, min_filler_repeat=2) is True


class TestFilterSegments:
    def test_removes_hallucinated(self):
        segments = [
            _seg(["the", "fire", "burns"]),
            _seg(["oh", "oh", "oh", "oh", "oh"]),
            _seg(["night", "falls", "slowly"]),
        ]
        result = filter_segments(segments)
        assert len(result) == 2
        assert result[0]["text"] == "the fire burns"
        assert result[1]["text"] == "night falls slowly"

    def test_keeps_all_valid(self):
        segments = [
            _seg(["hello", "world"]),
            _seg(["fire", "burns"]),
        ]
        result = filter_segments(segments)
        assert len(result) == 2

    def test_empty_input(self):
        assert filter_segments([]) == []
        assert filter_segments(None) is None

    def test_preserves_structure(self):
        segments = [_seg(["the", "fire", "burns"])]
        result = filter_segments(segments)
        assert len(result) == 1
        assert "start" in result[0]
        assert "end" in result[0]
        assert "text" in result[0]
        assert "words" in result[0]
