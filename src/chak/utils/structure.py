"""Musical structure analysis using librosa.

Analyzes tracks to produce per-section energy levels, transition points,
and beat density — driving emotionally intelligent image transitions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def analyze_track(audio_path: Path) -> dict:
    """Analyze a single audio track for musical structure.

    Returns a dict with sections, energy_curve, transition_points, beat_times.
    """
    import librosa
    from scipy.ndimage import uniform_filter1d

    logger.info("Analyzing structure: %s", audio_path.name)

    y, sr = librosa.load(str(audio_path), sr=22050)
    duration = librosa.get_duration(y=y, sr=sr)
    hop_length = 512
    window_sec = 2.0
    window_frames = int(window_sec * sr / hop_length)

    # ── 1. RMS Energy (normalized 0-1) ──
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    rms_norm = rms / (rms.max() + 1e-8)
    rms_times = librosa.frames_to_time(
        np.arange(len(rms)), sr=sr, hop_length=hop_length,
    )
    n_frames = len(rms)

    # ── 2. Spectral Flux (onset strength) ──
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    onset_norm = onset_env[:n_frames] / (onset_env[:n_frames].max() + 1e-8)

    # ── 3. Spectral Contrast (timbral complexity) ──
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr, hop_length=hop_length)
    contrast_mean = np.mean(contrast, axis=0)[:n_frames]
    contrast_norm = contrast_mean / (contrast_mean.max() + 1e-8)

    # ── 4. Beat Detection + Density ──
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)

    beat_density = np.zeros(n_frames)
    for bf in beat_frames:
        if bf < n_frames:
            lo = max(0, bf - window_frames // 2)
            hi = min(n_frames, bf + window_frames // 2)
            beat_density[lo:hi] += 1.0
    beat_density = uniform_filter1d(beat_density, size=max(1, window_frames))
    beat_density_norm = beat_density / (beat_density.max() + 1e-8)

    # ── 5. Composite Intensity Score ──
    # Ensure all arrays are same length
    min_len = min(len(rms_norm), len(onset_norm), len(contrast_norm), len(beat_density_norm))
    intensity = (
        0.35 * rms_norm[:min_len]
        + 0.30 * onset_norm[:min_len]
        + 0.20 * contrast_norm[:min_len]
        + 0.15 * beat_density_norm[:min_len]
    )
    smooth_size = max(1, window_frames // 2)
    intensity = uniform_filter1d(intensity, size=smooth_size)
    intensity = intensity / (intensity.max() + 1e-8)

    # ── 6. Section Detection (agglomerative on chroma) ──
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
    n_sections = max(3, int(duration / 20))
    bounds = librosa.segment.agglomerative(chroma, k=n_sections)
    bound_times_arr = librosa.frames_to_time(bounds, sr=sr, hop_length=hop_length)

    sections = []
    for i in range(len(bound_times_arr)):
        start = float(bound_times_arr[i])
        end = float(bound_times_arr[i + 1]) if i + 1 < len(bound_times_arr) else duration
        s_frame = int(start * sr / hop_length)
        e_frame = min(int(end * sr / hop_length), len(intensity))
        if e_frame <= s_frame:
            avg = 0.0
        else:
            avg = float(np.mean(intensity[s_frame:e_frame]))

        if avg < 0.33:
            energy_label = "low"
        elif avg < 0.66:
            energy_label = "medium"
        else:
            energy_label = "high"

        sections.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "energy": energy_label,
            "intensity": round(avg, 3),
        })

    # ── 7. Transition Points (peaks in spectral flux) ──
    onset_smooth = uniform_filter1d(onset_env[:n_frames], size=max(1, window_frames * 2))
    onset_diff = np.diff(onset_smooth)
    if len(onset_diff) > 0:
        threshold = np.percentile(np.abs(onset_diff), 90)
        transition_frames = np.where(onset_diff > threshold)[0]
        if len(transition_frames) > 0:
            # Merge close transitions (min 3s apart)
            merged = [transition_frames[0]]
            min_gap = int(3.0 * sr / hop_length)
            for f in transition_frames[1:]:
                if f - merged[-1] > min_gap:
                    merged.append(f)
            transition_times = librosa.frames_to_time(
                np.array(merged), sr=sr, hop_length=hop_length,
            ).tolist()
        else:
            transition_times = []
    else:
        transition_times = []

    # ── 8. Downsampled energy curve (~2 points/sec) ──
    downsample = max(1, len(intensity) // max(1, int(duration * 2)))
    energy_curve = [
        [round(float(rms_times[i]), 2), round(float(intensity[i]), 3)]
        for i in range(0, min(len(intensity), len(rms_times)), downsample)
    ]

    bpm_val = float(tempo) if np.isscalar(tempo) else float(tempo[0])

    result = {
        "duration": round(duration, 2),
        "bpm": round(bpm_val, 1),
        "sections": sections,
        "energy_curve": energy_curve,
        "transition_points": [round(t, 2) for t in transition_times],
        "beat_times": [round(float(t), 3) for t in beat_times],
    }

    logger.info(
        "%s: %.1fs, %.1f BPM, %d sections, %d transitions, %d beats",
        audio_path.name, duration, bpm_val,
        len(sections), len(transition_times), len(beat_times),
    )
    return result


def save_structure(structure: dict, out_path: Path) -> None:
    """Save structure analysis to JSON."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(structure, f, indent=2)
    logger.info("Saved structure -> %s", out_path)


def load_structure(track_id: str, album_dir: Path) -> dict | None:
    """Load cached structure analysis for a track."""
    path = album_dir / "data" / f"{track_id}.structure.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_intensity_at(structure: dict, time: float) -> float:
    """Get interpolated intensity at a specific time from energy curve."""
    curve = structure.get("energy_curve", [])
    if not curve:
        return 0.5

    # Find surrounding points
    for i in range(len(curve) - 1):
        t0, v0 = curve[i]
        t1, v1 = curve[i + 1]
        if t0 <= time <= t1:
            # Linear interpolation
            frac = (time - t0) / (t1 - t0) if t1 != t0 else 0.0
            return v0 + frac * (v1 - v0)

    # Before first or after last point
    if time <= curve[0][0]:
        return curve[0][1]
    return curve[-1][1]


def get_avg_intensity(structure: dict, start: float, end: float) -> float:
    """Get average intensity over a time range."""
    curve = structure.get("energy_curve", [])
    if not curve:
        return 0.5

    values = []
    for t, v in curve:
        if start <= t <= end:
            values.append(v)

    if not values:
        # No curve points in range — interpolate at midpoint
        return get_intensity_at(structure, (start + end) / 2)

    return sum(values) / len(values)


def analyze_album_tracks(album_dir: Path) -> dict[str, dict]:
    """Analyze structure for all tracks in an album.

    Reads album_config.json, runs analysis, caches results.
    """
    config_path = album_dir / "album_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"album_config.json not found in {album_dir}")

    with open(config_path, encoding="utf-8") as f:
        album_config = json.load(f)

    results: dict[str, dict] = {}
    for track in album_config.get("tracks", []):
        track_id = track.get("track_id") or track.get("id", "")
        slot = track.get("slot", 0)

        # Find audio file
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

        structure = analyze_track(audio_path)
        cache_path = album_dir / "data" / f"{track_id}.structure.json"
        save_structure(structure, cache_path)
        results[track_id] = structure

    return results
