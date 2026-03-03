"""Tests for chak.schemas — Pydantic model validation."""

import pytest
from pydantic import ValidationError

from chak.schemas import (
    AlbumConfig,
    AlignmentResult,
    AlignmentSegment,
    FusedTimelineEntry,
    FusedTrackData,
    MediaConcept,
    MediaEntry,
    MediaManifest,
    TimelineEntry,
    TimelineResult,
    TrackConfig,
    WordTiming,
)


class TestWordTiming:
    def test_valid(self):
        w = WordTiming(start=0.0, end=0.5, text="hello")
        assert w.start == 0.0
        assert w.text == "hello"

    def test_missing_field(self):
        with pytest.raises(ValidationError):
            WordTiming(start=0.0, end=0.5)


class TestAlignmentSegment:
    def test_valid_with_words(self):
        seg = AlignmentSegment(
            start=0.0, end=2.0, text="hello world",
            words=[WordTiming(start=0.0, end=0.5, text="hello")]
        )
        assert len(seg.words) == 1

    def test_valid_without_words(self):
        seg = AlignmentSegment(start=0.0, end=2.0, text="hello world")
        assert seg.words == []


class TestAlignmentResult:
    def test_valid(self):
        result = AlignmentResult(id="track_01", segments=[])
        assert result.id == "track_01"
        assert result.confidence == "normal"

    def test_low_confidence(self):
        result = AlignmentResult(id="track_02", segments=[], confidence="low")
        assert result.confidence == "low"


class TestTimelineEntry:
    def test_valid(self):
        entry = TimelineEntry(
            id="line_0_occ_0", start=0.0, end=2.0, lyric="Hello"
        )
        assert entry.line_index is None
        assert entry.occurrence_index == 0

    def test_with_line_index(self):
        entry = TimelineEntry(
            id="line_5_occ_1", line_index=5, occurrence_index=1,
            start=10.0, end=12.0, lyric="Fire burns"
        )
        assert entry.line_index == 5


class TestAlbumConfig:
    def test_valid(self):
        config = AlbumConfig(
            album_id="TEST_001",
            title="Test Album",
            tracks=[
                TrackConfig(
                    slot=1, track_id="track_01",
                    variant_id="v1", audio_path="audio/01.mp3"
                )
            ]
        )
        assert config.album_id == "TEST_001"
        assert len(config.tracks) == 1

    def test_empty_tracks_fails(self):
        with pytest.raises(ValidationError):
            AlbumConfig(
                album_id="TEST_001",
                title="Test Album",
                tracks=[]
            )

    def test_missing_title_fails(self):
        with pytest.raises(ValidationError):
            AlbumConfig(
                album_id="TEST_001",
                tracks=[
                    TrackConfig(
                        slot=1, track_id="track_01",
                        variant_id="v1", audio_path="audio/01.mp3"
                    )
                ]
            )


class TestMediaManifest:
    def test_empty(self):
        m = MediaManifest()
        assert m.concepts == {}

    def test_with_concepts(self):
        m = MediaManifest(concepts={
            "a magical forest": MediaConcept(filename="img001.jpg", status="ok"),
            "dark night": MediaConcept(filename="img002.jpg", status="failed"),
        })
        assert m.concepts["a magical forest"].status == "ok"
        assert m.concepts["dark night"].status == "failed"

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            MediaConcept(filename="img.jpg", status="unknown")


class TestFusedTrackData:
    def test_valid(self):
        entry = FusedTimelineEntry(
            id="line_0_occ_0", start=0.0, end=2.0, lyric="Hello",
            real_meaning="Greeting",
            media=[MediaEntry(offset=0.0, url="media/img.jpg", query="hello")],
            words=[WordTiming(start=0.0, end=0.5, text="Hello")],
        )
        track = FusedTrackData(
            id="track_01", album_id="TEST_001", timeline=[entry]
        )
        assert len(track.timeline) == 1
        assert track.timeline[0].media[0].url == "media/img.jpg"

    def test_empty_timeline(self):
        track = FusedTrackData(id="track_01", album_id="TEST_001", timeline=[])
        assert len(track.timeline) == 0
