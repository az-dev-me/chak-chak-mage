"""Tests for chak.utils.text — text normalization utilities."""

import pytest
from chak.utils.text import STOPWORDS, normalize, norm_tokens


class TestNormalize:
    def test_basic_lowercase(self):
        assert normalize("Hello World") == ["hello", "world"]

    def test_strips_punctuation(self):
        assert normalize("don't, stop!") == ["don", "t", "stop"]

    def test_strips_special_chars(self):
        assert normalize("fire—the—flame") == ["fire", "the", "flame"]

    def test_empty_string(self):
        assert normalize("") == []

    def test_none_is_empty(self):
        assert normalize(None) == []

    def test_whitespace_only(self):
        assert normalize("   \t\n  ") == []

    def test_numbers_preserved(self):
        assert normalize("Track 01") == ["track", "01"]

    def test_mixed_case_unicode(self):
        assert normalize("FIRE RUN 🔥") == ["fire", "run"]

    def test_already_clean(self):
        assert normalize("hello") == ["hello"]


class TestNormTokens:
    def test_removes_stopwords(self):
        result = norm_tokens("the fire is burning in the night")
        assert "the" not in result
        assert "is" not in result
        assert "in" not in result
        assert "fire" in result
        assert "burning" in result
        assert "night" in result

    def test_removes_vocal_fillers(self):
        result = norm_tokens("oh yeah the music is playing")
        assert "oh" not in result
        assert "yeah" not in result
        assert "music" in result
        assert "playing" in result

    def test_empty_string(self):
        assert norm_tokens("") == []

    def test_none_returns_empty(self):
        assert norm_tokens(None) == []

    def test_custom_stopwords(self):
        result = norm_tokens("hello world", stopwords=frozenset({"hello"}))
        assert result == ["world"]

    def test_single_char_removed(self):
        # Tokens with len <= 1 are filtered
        result = norm_tokens("I am a star")
        assert "i" not in result
        assert "a" not in result

    def test_preserves_apostrophe(self):
        result = norm_tokens("don't stop believing")
        assert "don't" in result
        assert "stop" in result
        assert "believing" in result


class TestStopwords:
    def test_contains_common_words(self):
        for w in ["the", "a", "is", "and", "or", "but", "to", "of"]:
            assert w in STOPWORDS

    def test_contains_vocal_fillers(self):
        for w in ["oh", "ooh", "ah", "yeah", "mm", "hey"]:
            assert w in STOPWORDS

    def test_does_not_contain_content_words(self):
        for w in ["fire", "music", "night", "run", "burning"]:
            assert w not in STOPWORDS
