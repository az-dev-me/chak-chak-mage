"""Classify aligned RAW MP3s into per-track Choice Kit folders.

Uses TF-IDF cosine similarity to score each Whisper transcript against
canonical lyrics from base_semantic_matrix.json.

Special rules:
- TTS files (from filesTTS.zip) are split between track_01 and track_09
- Music tracks (02-08) must have even variant counts (pair rule)
- Empty music tracks get filled from unassigned pool

Ported from pipeline/raw_catalog_classify.py.
"""

from __future__ import annotations

import logging
import math
import os
import shutil
from collections import Counter
from pathlib import Path

from chak.utils.io import ensure_dir, load_json, write_json
from chak.utils.text import norm_tokens

logger = logging.getLogger(__name__)

MUSIC_TRACKS = [
    "track_02", "track_03", "track_04", "track_05",
    "track_06", "track_07", "track_08",
]


def _build_idf_smoothed(track_counters: dict[str, Counter]) -> dict[str, float]:
    """Build IDF table with Laplace smoothing over canonical track docs.

    Uses log((N+1)/(df+1)) + 1.0 to match the original classify script.
    Only canonical docs contribute to IDF (stable across RAW batches).
    """
    docs = list(track_counters.values())
    n = len(docs)
    df: Counter[str] = Counter()
    for c in docs:
        for tok in c:
            df[tok] += 1
    return {tok: math.log((n + 1) / (d + 1)) + 1.0 for tok, d in df.items()}


def _cosine_tfidf(a: Counter, b: Counter, idf: dict[str, float]) -> float:
    """Cosine similarity with TF-IDF weighting (smoothed IDF)."""
    if not a or not b:
        return 0.0
    dot = na = nb = 0.0
    for tok, tf_a in a.items():
        w_a = float(tf_a) * idf.get(tok, 0.0)
        na += w_a * w_a
        tf_b = b.get(tok)
        if tf_b:
            w_b = float(tf_b) * idf.get(tok, 0.0)
            dot += w_a * w_b
    for tok, tf_b in b.items():
        w_b = float(tf_b) * idf.get(tok, 0.0)
        nb += w_b * w_b
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def load_base_track_tokens(semantics_path: Path) -> dict[str, Counter]:
    """Load canonical lyrics as normalized token counters per track."""
    data = load_json(semantics_path)
    out: dict[str, Counter] = {}
    for track_id, payload in data.items():
        lines = payload.get("lines", [])
        lyrics = " ".join(str(x.get("lyric", "")) for x in lines)
        out[track_id] = Counter(norm_tokens(lyrics))
    return out


def _load_transcript_tokens(words_json_path: Path) -> list[str]:
    """Load a Whisper alignment file and return normalized tokens."""
    data = load_json(words_json_path)
    segs = data.get("segments", [])
    full = " ".join(str(s.get("text", "")) for s in segs)
    return norm_tokens(full)


def _get_tts_stems(choicekit_dir: Path) -> list[str]:
    """Get stems (raw_id) of MP3s sourced from filesTTS.zip."""
    index_path = choicekit_dir / "RAW_index.json"
    if not index_path.exists():
        return []
    index = load_json(index_path)
    if not isinstance(index, list):
        return []
    stems = []
    for entry in index:
        name = entry.get("name", "")
        source = entry.get("source_zip", "") or ""
        if name.lower().endswith(".mp3") and "filesTTS" in source:
            stems.append(os.path.splitext(name)[0])
    return sorted(stems)


def _classify_batch(
    base: dict[str, Counter],
    raw_alignment_dir: Path,
    min_score: float,
    min_margin: float,
    high_score: float,
    only_tracks: list[str] | None = None,
    only_stems: set[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Score alignment files against canonical tracks.

    Returns (assigned, unassigned).
    """
    assigned: list[dict] = []
    unassigned: list[dict] = []
    tracks = only_tracks or list(base.keys())
    base_sub = {k: base[k] for k in tracks if k in base}
    idf = _build_idf_smoothed(base_sub)

    for fname in sorted(os.listdir(raw_alignment_dir)):
        if not fname.endswith("_words.json"):
            continue
        stem = fname[: -len("_words.json")]
        if only_stems is not None and stem not in only_stems:
            continue

        tokens = _load_transcript_tokens(raw_alignment_dir / fname)
        t_counter = Counter(tokens)

        scored = [
            (track_id, _cosine_tfidf(t_counter, base_sub[track_id], idf))
            for track_id in tracks if track_id in base_sub
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        if not scored:
            continue

        best_id, best_score = scored[0]
        second_score = scored[1][1] if len(scored) > 1 else 0.0
        margin = best_score - second_score

        rec = {
            "raw_id": stem,
            "best_track": best_id,
            "best_score": round(best_score, 4),
            "second_score": round(second_score, 4),
            "margin": round(margin, 4),
        }

        ok = False
        reason = "low_score"
        if best_score >= min_score and margin >= min_margin:
            ok = True
            reason = "margin_ok"
        elif best_score >= high_score:
            ok = True
            reason = "high_score"

        rec["reason"] = reason
        (assigned if ok else unassigned).append(rec)

    return assigned, unassigned


def _ensure_track_folder(
    choicekit_dir: Path,
    track_id: str,
    track_names: dict[str, str],
) -> Path:
    """Create and return the TRACK_XX_Name folder path."""
    name = track_names.get(track_id, track_id)
    num = track_id.replace("track_", "")
    folder_name = f"TRACK_{num}_{name}"
    folder = choicekit_dir / folder_name
    ensure_dir(folder)
    return folder


def _fill_empty_tracks(
    music_assigned: list[dict],
    music_unassigned: list[dict],
) -> None:
    """Ensure every music track has at least one assignment."""
    assigned_tracks = {r["best_track"] for r in music_assigned}
    for track_id in MUSIC_TRACKS:
        if track_id in assigned_tracks:
            continue
        # Try candidates whose best_track matches
        candidates = [u for u in music_unassigned if u["best_track"] == track_id]
        if candidates:
            best = max(candidates, key=lambda u: u["best_score"])
            best["reason"] = "fallback_empty_track"
            music_assigned.append(best)
            music_unassigned.remove(best)
        elif music_unassigned:
            # No match for this track — take lowest-scoring unassigned
            worst = min(music_unassigned, key=lambda u: u["best_score"])
            worst = dict(worst)
            worst["best_track"] = track_id
            worst["reason"] = "fallback_empty_track"
            music_assigned.append(worst)
            music_unassigned.remove(
                next(u for u in music_unassigned if u["raw_id"] == worst["raw_id"])
            )
        else:
            logger.warning("Empty %s and no unassigned left to fill it.", track_id)
        assigned_tracks.add(track_id)


def _enforce_pair_rule(
    music_assigned: list[dict],
    music_unassigned: list[dict],
) -> None:
    """Ensure every music track has even count (pair rule).

    Adds from unassigned, or moves between tracks if needed.
    """
    def _counts() -> dict[str, int]:
        c: dict[str, int] = {}
        for r in music_assigned:
            t = r["best_track"]
            c[t] = c.get(t, 0) + 1
        return c

    max_iterations = 50  # safety valve
    for _ in range(max_iterations):
        counts = _counts()
        odd_tracks = [t for t in MUSIC_TRACKS if counts.get(t, 0) % 2 != 0]
        if not odd_tracks:
            break

        odd_tracks.sort(key=lambda t: counts.get(t, 0))
        track_id = odd_tracks[0]

        # Try from unassigned
        candidates = [u for u in music_unassigned if u["best_track"] == track_id]
        if candidates:
            best = max(candidates, key=lambda u: u["best_score"])
            best["reason"] = "fallback_pair"
            music_assigned.append(best)
            music_unassigned.remove(best)
            continue

        if music_unassigned:
            worst = min(music_unassigned, key=lambda u: u["best_score"])
            worst = dict(worst)
            worst["best_track"] = track_id
            worst["reason"] = "fallback_pair"
            music_assigned.append(worst)
            music_unassigned.remove(
                next(u for u in music_unassigned if u["raw_id"] == worst["raw_id"])
            )
            continue

        # Move from a donor track with 3+
        donor = next(
            (t for t in MUSIC_TRACKS
             if counts.get(t, 0) >= 3 and counts.get(t, 0) % 2 != 0),
            None,
        )
        if not donor:
            logger.warning("Pair rule: cannot fix odd %s (no donor).", track_id)
            break

        donor_recs = [r for r in music_assigned if r["best_track"] == donor]
        to_move = min(donor_recs, key=lambda r: r["best_score"])
        music_assigned.remove(to_move)
        to_move = dict(to_move)
        to_move["best_track"] = track_id
        to_move["reason"] = "fallback_pair"
        music_assigned.append(to_move)


def classify_raw_catalog(
    choicekit_dir: Path,
    semantics_path: Path,
    track_names: dict[str, str],
    *,
    min_score: float = 0.05,
    min_margin: float = 0.01,
    high_score: float = 0.45,
    clear_tracks: bool = False,
) -> dict:
    """Run full classification: score, assign, organize, write report.

    Returns the classification report dict.
    """
    raw_dir = choicekit_dir / "RAW"
    raw_alignment = raw_dir / "alignment"
    if not raw_alignment.is_dir():
        raise FileNotFoundError(
            f"RAW alignment not found at {raw_alignment}. "
            "Run 'chak catalog align-raw' first."
        )

    base = load_base_track_tokens(semantics_path)

    # Split TTS stems from music stems
    tts_stems = _get_tts_stems(choicekit_dir)
    all_stems: set[str] = set()
    for fname in os.listdir(raw_alignment):
        if fname.endswith("_words.json"):
            all_stems.add(fname[: -len("_words.json")])
    music_stems = all_stems - set(tts_stems)

    # TTS files → split between track_01 and track_09
    tts_assigned: list[dict] = []
    if tts_stems:
        mid = (len(tts_stems) + 1) // 2
        for i, stem in enumerate(tts_stems):
            track_id = "track_01" if i < mid else "track_09"
            tts_assigned.append({
                "raw_id": stem,
                "best_track": track_id,
                "best_score": 1.0,
                "second_score": 0.0,
                "margin": 1.0,
                "reason": "tts",
            })

    # Classify music stems against music tracks only
    music_assigned, music_unassigned = _classify_batch(
        base, raw_alignment, min_score, min_margin, high_score,
        only_tracks=MUSIC_TRACKS,
        only_stems=music_stems if music_stems else None,
    )

    # Ensure no empty music tracks
    _fill_empty_tracks(music_assigned, music_unassigned)

    # Enforce even counts (pair rule)
    _enforce_pair_rule(music_assigned, music_unassigned)

    assigned = tts_assigned + music_assigned
    unassigned = music_unassigned

    # Write classification report
    report = {"assigned": assigned, "unassigned": unassigned}
    report_path = choicekit_dir / "classification_report.json"
    write_json(report_path, report)
    logger.info(
        "Classification: %d assigned, %d unassigned -> %s",
        len(assigned), len(unassigned), report_path,
    )

    # Clear existing track folders if requested
    if clear_tracks:
        for item in choicekit_dir.iterdir():
            if item.is_dir() and item.name.upper().startswith("TRACK_"):
                shutil.rmtree(item, ignore_errors=True)

    # Copy assigned MP3s into per-track folders
    per_track_counts: dict[str, int] = {}
    catalog_tracks: list[dict] = []

    for rec in assigned:
        track_id = rec["best_track"]
        raw_id = rec["raw_id"]
        src_mp3 = raw_dir / f"{raw_id}.mp3"

        if not src_mp3.exists():
            # Handle collision-suffixed names
            candidates = [
                f for f in os.listdir(raw_dir)
                if f.startswith(raw_id) and f.lower().endswith(".mp3")
            ]
            if not candidates:
                continue
            src_mp3 = raw_dir / candidates[0]

        track_folder = _ensure_track_folder(choicekit_dir, track_id, track_names)
        n = per_track_counts.get(track_id, 0) + 1
        per_track_counts[track_id] = n

        variant_id = f"{track_id.replace('track_', 'Track_')}_Variant{n}"

        # Keep original RAW filename for traceability
        dest_path = track_folder / src_mp3.name
        if not dest_path.exists():
            shutil.copy2(src_mp3, dest_path)

        # Relative path from Choice Kit parent (ORANGE_BOX)
        try:
            rel = str(dest_path.relative_to(choicekit_dir.parent)).replace("\\", "/")
        except ValueError:
            rel = str(dest_path)

        catalog_tracks.append({
            "track_id": track_id,
            "variant_id": variant_id,
            "audio_path": rel,
        })

    # Write catalog_mapping.json
    catalog_path = choicekit_dir / "catalog_mapping.json"
    write_json(catalog_path, {"tracks": catalog_tracks})
    logger.info("Wrote catalog_mapping.json -> %s (%d entries)", catalog_path, len(catalog_tracks))

    return report
