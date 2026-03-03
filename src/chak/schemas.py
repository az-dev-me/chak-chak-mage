"""Pydantic models for all pipeline JSON contracts.

Validates data at every stage boundary to catch silent corruption.
See DATA_CONTRACTS.md for field-level documentation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ── Word-level alignment ─────────────────────────────────


class WordTiming(BaseModel):
    start: float
    end: float
    text: str


class AlignmentSegment(BaseModel):
    start: float
    end: float
    text: str
    words: list[WordTiming] = Field(default_factory=list)


class AlignmentResult(BaseModel):
    id: str
    segments: list[AlignmentSegment] = Field(default_factory=list)
    confidence: str = "normal"  # "normal" or "low" (for music tracks)


# ── Timeline ─────────────────────────────────────────────


class TimelineEntry(BaseModel):
    id: str
    line_index: int | None = None
    occurrence_index: int = 0
    start: float
    end: float
    lyric: str


class TimelineResult(BaseModel):
    id: str
    timeline: list[TimelineEntry] = Field(default_factory=list)


# ── Semantic data ────────────────────────────────────────


class SemanticLine(BaseModel):
    line_index: int
    lyric: str
    real_meaning: str = ""
    media_queries: list[str] = Field(default_factory=list)


class SemanticTrack(BaseModel):
    id: str
    lines: list[SemanticLine] = Field(default_factory=list)


# ── Media manifest ───────────────────────────────────────


class MediaConcept(BaseModel):
    filename: str
    status: Literal["pending", "ok", "failed"] = "pending"


class MediaManifest(BaseModel):
    concepts: dict[str, MediaConcept] = Field(default_factory=dict)


# ── Fused track data (player-ready) ─────────────────────


class MediaEntry(BaseModel):
    offset: float = 0.0
    url: str
    query: str = ""


class FusedTimelineEntry(BaseModel):
    id: str
    start: float
    end: float
    lyric: str
    real_meaning: str = ""
    media: list[MediaEntry] = Field(default_factory=list)
    words: list[WordTiming] = Field(default_factory=list)


class FusedTrackData(BaseModel):
    id: str
    album_id: str
    timeline: list[FusedTimelineEntry] = Field(default_factory=list)
    beat_times: list[float] = Field(default_factory=list)
    energy_curve: list[list[float]] = Field(default_factory=list)
    bpm: float = 0.0


# ── Album configuration ─────────────────────────────────


class TrackConfig(BaseModel):
    slot: int
    track_id: str
    variant_id: str
    audio_path: str


class AlbumConfig(BaseModel):
    album_id: str
    title: str
    artist: str = ""
    description: str = ""
    source: str = ""
    tracks: list[TrackConfig] = Field(min_length=1)


# ── Catalog mapping ─────────────────────────────────────


class CatalogTrackEntry(BaseModel):
    track_id: str
    variant_id: str
    audio_path: str


class CatalogMapping(BaseModel):
    tracks: list[CatalogTrackEntry] = Field(default_factory=list)


# ── Album index (generated) ─────────────────────────────


class AlbumIndexEntry(BaseModel):
    album_id: str
    title: str
    description: str = ""
    config: dict = Field(default_factory=dict)
