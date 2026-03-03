"""Beat detection utility using librosa.

Detects musical beats in audio tracks and caches results for use
by the fuse stage to create beat-synced image transitions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def detect_beats(audio_path: Path) -> list[float]:
    """Detect beat timestamps in an audio file.

    Returns a sorted list of beat times in seconds.
    """
    import librosa

    y, sr = librosa.load(str(audio_path), sr=22050)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    return sorted(round(float(t), 3) for t in beat_times)


def save_beats(beat_times: list[float], out_path: Path) -> None:
    """Save beat timestamps to a JSON cache file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"beats": beat_times, "count": len(beat_times)}, f, indent=2)
    logger.info("Saved %d beats -> %s", len(beat_times), out_path)


def load_beats(track_id: str, album_dir: Path) -> list[float]:
    """Load cached beat timestamps for a track.

    Returns empty list if no cache file exists.
    """
    beats_path = album_dir / "data" / f"{track_id}.beats.json"
    if not beats_path.exists():
        return []
    with open(beats_path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("beats", [])


def beats_in_range(
    beats: list[float], start: float, end: float,
    min_gap: float = 0.5,
) -> list[float]:
    """Filter beat timestamps to those within [start + min_gap, end - min_gap).

    The min_gap ensures the establishing image is visible for at least
    0.5s before the first beat transition, and transitions don't fire
    right at the end of a line. Without this, beats right at line
    boundaries cause invisible (<40ms) image flashes that the browser's
    ~250ms timeupdate interval can't catch.
    """
    return [b for b in beats if (start + min_gap) < b < (end - min_gap)]


def detect_album_beats(album_dir: Path) -> dict[str, list[float]]:
    """Detect beats for all tracks in an album.

    Reads album_config.json to find audio files, runs detection,
    and caches results per track.
    """
    config_path = album_dir / "album_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"album_config.json not found in {album_dir}")

    with open(config_path, encoding="utf-8") as f:
        album_config = json.load(f)

    results: dict[str, list[float]] = {}
    for track in album_config.get("tracks", []):
        track_id = track.get("track_id") or track.get("id", "")
        slot = track.get("slot", 0)

        # Try multiple audio path patterns
        audio_path = None
        candidates = [
            album_dir / f"{slot:02d} - {track_id}.mp3",
            album_dir / track.get("audioFile", ""),
        ]
        for candidate in candidates:
            if candidate.exists():
                audio_path = candidate
                break

        if not audio_path or not audio_path.exists():
            logger.warning("Audio not found for %s, tried: %s", track_id, candidates)
            continue

        logger.info("Detecting beats for %s...", track_id)
        beat_times = detect_beats(audio_path)
        cache_path = album_dir / "data" / f"{track_id}.beats.json"
        save_beats(beat_times, cache_path)
        results[track_id] = beat_times
        logger.info("%s: %d beats detected", track_id, len(beat_times))

    return results
