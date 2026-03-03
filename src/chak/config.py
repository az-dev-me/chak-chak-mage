"""Configuration loader for chak_pipeline.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from chak.utils.io import resolve_project_root


@dataclass
class HallucinationConfig:
    filler_tokens: frozenset[str] = frozenset()
    min_filler_repeat: int = 2
    min_any_repeat: int = 8
    min_total_for_all_filler: int = 3
    min_filler_count: int = 5
    max_single_token_repeat: int = 25


@dataclass
class AlignmentConfig:
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    language: str = "en"
    compression_ratio_threshold: float = 2.0
    condition_on_previous_text: bool = False
    hallucination: HallucinationConfig = field(default_factory=HallucinationConfig)


@dataclass
class TimelineConfig:
    min_similarity: float = 0.45
    music_track_similarity: float = 0.25
    music_tracks: list[str] = field(default_factory=lambda: [
        "track_02", "track_03", "track_04",
        "track_05", "track_06", "track_07", "track_08",
    ])


@dataclass
class MediaConfig:
    provider: str = "stable_horde"
    fallback_provider: str = "placeholder"
    max_prompt_length: int = 180
    request_delay: float = 1.0
    timeout: int = 90
    max_retries: int = 2
    image_width: int = 768
    image_height: int = 576
    api_key: str = ""  # Pollinations API key (or set POLLINATIONS_API_KEY env var)
    # Local GPU generation settings (provider = "local_gpu")
    gpu_device: str = "cuda:1"
    model_id: str = "stabilityai/stable-diffusion-2-1"
    num_inference_steps: int = 25
    guidance_scale: float = 7.5


@dataclass
class FrontendConfig:
    display_max_words: int = 35
    display_max_chars: int = 320
    word_epsilon: float = 0.05


@dataclass
class TracksConfig:
    names: dict[str, str] = field(default_factory=dict)
    titles: dict[str, str] = field(default_factory=dict)


@dataclass
class PipelineConfig:
    alignment: AlignmentConfig = field(default_factory=AlignmentConfig)
    timeline: TimelineConfig = field(default_factory=TimelineConfig)
    media: MediaConfig = field(default_factory=MediaConfig)
    frontend: FrontendConfig = field(default_factory=FrontendConfig)
    tracks: TracksConfig = field(default_factory=TracksConfig)

    # Resolved paths (set after loading)
    project_root: Path = field(default_factory=lambda: Path("."))


def _build_hallucination_config(raw: dict[str, Any]) -> HallucinationConfig:
    return HallucinationConfig(
        filler_tokens=frozenset(raw.get("filler_tokens", [])),
        min_filler_repeat=raw.get("min_filler_repeat", 2),
        min_any_repeat=raw.get("min_any_repeat", 8),
        min_total_for_all_filler=raw.get("min_total_for_all_filler", 3),
        min_filler_count=raw.get("min_filler_count", 5),
        max_single_token_repeat=raw.get("max_single_token_repeat", 25),
    )


def load_config(config_path: str | Path | None = None) -> PipelineConfig:
    """Load pipeline configuration from chak_pipeline.toml.

    If *config_path* is None, searches upward from the current file for
    ``chak_pipeline.toml``.
    """
    if config_path is None:
        root = resolve_project_root()
        config_path = root / "chak_pipeline.toml"
    else:
        config_path = Path(config_path)
        root = config_path.parent

    if not config_path.exists():
        # Return defaults if no config file found
        return PipelineConfig(project_root=root)

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    raw_alignment = raw.get("alignment", {})
    raw_hallucination = raw_alignment.pop("hallucination", {})

    alignment = AlignmentConfig(
        whisper_model=raw_alignment.get("whisper_model", "base"),
        whisper_device=raw_alignment.get("whisper_device", "cpu"),
        language=raw_alignment.get("language", "en"),
        compression_ratio_threshold=raw_alignment.get("compression_ratio_threshold", 2.0),
        condition_on_previous_text=raw_alignment.get("condition_on_previous_text", False),
        hallucination=_build_hallucination_config(raw_hallucination),
    )

    raw_timeline = raw.get("timeline", {})
    timeline = TimelineConfig(
        min_similarity=raw_timeline.get("min_similarity", 0.45),
        music_track_similarity=raw_timeline.get("music_track_similarity", 0.25),
        music_tracks=raw_timeline.get("music_tracks", []),
    )

    raw_media = raw.get("media", {})
    media = MediaConfig(
        provider=raw_media.get("provider", "pollinations"),
        fallback_provider=raw_media.get("fallback_provider", "local"),
        max_prompt_length=raw_media.get("max_prompt_length", 180),
        request_delay=raw_media.get("request_delay", 1.0),
        timeout=raw_media.get("timeout", 90),
        max_retries=raw_media.get("max_retries", 3),
        image_width=raw_media.get("image_width", 1024),
        image_height=raw_media.get("image_height", 576),
        api_key=raw_media.get("api_key", ""),
        gpu_device=raw_media.get("gpu_device", "cuda:1"),
        model_id=raw_media.get("model_id", "stabilityai/stable-diffusion-2-1"),
        num_inference_steps=raw_media.get("num_inference_steps", 25),
        guidance_scale=raw_media.get("guidance_scale", 7.5),
    )

    raw_frontend = raw.get("frontend", {})
    frontend = FrontendConfig(
        display_max_words=raw_frontend.get("display_max_words", 35),
        display_max_chars=raw_frontend.get("display_max_chars", 320),
        word_epsilon=raw_frontend.get("word_epsilon", 0.05),
    )

    raw_tracks = raw.get("tracks", {})
    tracks = TracksConfig(
        names=dict(raw_tracks.get("names", {})),
        titles=dict(raw_tracks.get("titles", {})),
    )

    return PipelineConfig(
        alignment=alignment,
        timeline=timeline,
        media=media,
        frontend=frontend,
        tracks=tracks,
        project_root=root,
    )
