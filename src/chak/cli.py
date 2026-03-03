"""Unified CLI for the Chak Chak Mage pipeline.

Single entry point replacing 25 separate scripts.

Catalog commands (archive → catalog):
    chak catalog extract --zips Archive/files.zip Archive/filesTTS.zip ...
    chak catalog align-raw [--limit N] [--force]
    chak catalog classify [--clear-tracks]
    chak catalog build <album_id> [--title "..."]
    chak catalog status

Album build commands (catalog → player):
    chak build <album_id>
    chak build --from-catalog
    chak build-all
    chak align <album_id> [--track track_02]
    chak timeline <album_id>
    chak media-prep <album_id>
    chak media-fetch <album_id> [--reset-failed]
    chak fuse <album_id>
    chak export <album_id>
    chak validate <album_id>
    chak index
    chak status <album_id>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from chak.config import load_config


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


def cmd_build(args: argparse.Namespace) -> None:
    """Build a single album end-to-end."""
    from chak.orchestrator import build_album, build_from_catalog

    config = load_config(args.config)

    if args.from_catalog:
        project_root = config.project_root
        selected = Path(args.selected) if args.selected else (
            project_root.parent / "THE_CHAK_CHAK_MAGE_CHOICE_KIT" / "selected_album.json"
        )
        mapping = Path(args.mapping) if args.mapping else (
            project_root / "catalog_mapping.json"
        )
        album_id = build_from_catalog(selected, mapping, config)
        print(f"Built album from catalog: {album_id}")
    else:
        if not args.album_id:
            print("Error: album_id is required (or use --from-catalog)", file=sys.stderr)
            sys.exit(1)
        summary = build_album(
            args.album_id, config,
            skip_alignment=args.skip_alignment,
            skip_media=args.skip_media,
            reset_failed_media=args.reset_failed,
        )
        print(f"Build complete: {summary}")


def cmd_build_all(args: argparse.Namespace) -> None:
    """Rebuild all albums."""
    from chak.orchestrator import build_all

    config = load_config(args.config)
    summaries = build_all(config)
    for s in summaries:
        print(f"  {s['album_id']}: {s['tracks']} tracks, {s['concepts_ok']}/{s['concepts_total']} media ok")


def cmd_align(args: argparse.Namespace) -> None:
    """Run alignment only."""
    from chak.stages.align import align_album_tracks

    config = load_config(args.config)
    album_dir = config.project_root / "albums" / args.album_id
    results = align_album_tracks(album_dir, config, track_id=args.track)
    print(f"Aligned {len(results)} tracks")


def cmd_timeline(args: argparse.Namespace) -> None:
    """Run timeline building only."""
    from chak.stages.timeline import build_album_timelines

    config = load_config(args.config)
    album_dir = config.project_root / "albums" / args.album_id
    results = build_album_timelines(album_dir, config, track_id=args.track)
    print(f"Built {len(results)} timelines")


def cmd_media_prep(args: argparse.Namespace) -> None:
    """Run media manifest preparation only."""
    from chak.stages.manifest import prepare_manifest

    config = load_config(args.config)
    album_dir = config.project_root / "albums" / args.album_id
    manifest = prepare_manifest(album_dir, config)
    print(f"Manifest: {len(manifest.concepts)} concepts")


def cmd_media_fetch(args: argparse.Namespace) -> None:
    """Run media fetching only."""
    from chak.stages.fetch_media import fetch_album_media

    config = load_config(args.config)
    album_dir = config.project_root / "albums" / args.album_id
    seed_dir = Path(args.seed_dir) if args.seed_dir else None
    manifest = fetch_album_media(
        album_dir, config,
        reset_failed=args.reset_failed,
        reset_placeholders=args.reset_placeholders,
        max_requests=args.max_requests,
        seed_dir=seed_dir,
    )
    ok = sum(1 for c in manifest.concepts.values() if c.status == "ok")
    total = len(manifest.concepts)
    print(f"Media: {ok}/{total} ok")


def cmd_fuse(args: argparse.Namespace) -> None:
    """Run fusion only."""
    from chak.stages.fuse import fuse_album_tracks

    config = load_config(args.config)
    album_dir = config.project_root / "albums" / args.album_id
    results = fuse_album_tracks(album_dir, config, track_id=args.track)
    print(f"Fused {len(results)} tracks")


def cmd_export(args: argparse.Namespace) -> None:
    """Run JS export only."""
    from chak.stages.fuse import fuse_album_tracks
    from chak.stages.export_js import export_album_tracks, generate_albums_index

    config = load_config(args.config)
    album_dir = config.project_root / "albums" / args.album_id
    fused = fuse_album_tracks(album_dir, config)
    export_album_tracks(album_dir, args.album_id, fused)
    generate_albums_index(config)
    print(f"Exported {len(fused)} tracks for {args.album_id}")


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate album data."""
    from chak.stages.sanitize import validate_album_alignments

    config = load_config(args.config)
    album_dir = config.project_root / "albums" / args.album_id
    reports = validate_album_alignments(album_dir, config)
    issues = sum(1 for r in reports if not r.is_clean)
    if issues:
        print(f"Validation: {issues} files have hallucinated segments")
        sys.exit(1)
    else:
        print(f"Validation: all {len(reports)} files clean")


def cmd_index(args: argparse.Namespace) -> None:
    """Regenerate albums index."""
    from chak.stages.export_js import generate_albums_index

    config = load_config(args.config)
    generate_albums_index(config)
    print("Albums index regenerated")


def cmd_catalog(args: argparse.Namespace) -> None:
    """Dispatch catalog subcommands."""
    args.catalog_func(args)


def cmd_catalog_extract(args: argparse.Namespace) -> None:
    """Extract MP3s from archive zips into Choice Kit RAW/."""
    from chak.catalog.extract import extract_and_index

    config = load_config(args.config)
    repo_root = config.project_root.parent
    choicekit_dir = repo_root / "THE_CHAK_CHAK_MAGE_CHOICE_KIT"

    if args.choicekit:
        choicekit_dir = Path(args.choicekit)

    entries = extract_and_index(args.zips, choicekit_dir, repo_root)
    new = sum(1 for e in entries if not e.get("deduped"))
    duped = sum(1 for e in entries if e.get("deduped"))
    print(f"Extracted {len(entries)} MP3s ({new} new, {duped} deduped)")


def cmd_catalog_align_raw(args: argparse.Namespace) -> None:
    """Align all RAW MP3s with Whisper for classification."""
    from chak.stages.align import align_raw_catalog

    config = load_config(args.config)
    repo_root = config.project_root.parent
    choicekit_dir = repo_root / "THE_CHAK_CHAK_MAGE_CHOICE_KIT"

    if args.choicekit:
        choicekit_dir = Path(args.choicekit)

    count = align_raw_catalog(
        choicekit_dir, config,
        limit=args.limit,
        force=args.force,
    )
    print(f"Aligned {count} RAW files")


def cmd_catalog_classify(args: argparse.Namespace) -> None:
    """Classify aligned RAW files into per-track folders."""
    from chak.catalog.classify import classify_raw_catalog

    config = load_config(args.config)
    repo_root = config.project_root.parent
    choicekit_dir = repo_root / "THE_CHAK_CHAK_MAGE_CHOICE_KIT"
    semantics = config.project_root / "shared" / "semantics" / "base_semantic_matrix.json"

    if args.choicekit:
        choicekit_dir = Path(args.choicekit)

    report = classify_raw_catalog(
        choicekit_dir, semantics, config.tracks.names,
        min_score=args.min_score,
        min_margin=args.min_margin,
        high_score=args.high_score,
        clear_tracks=args.clear_tracks,
    )

    n_assigned = len(report.get("assigned", []))
    n_unassigned = len(report.get("unassigned", []))
    print(f"Classification: {n_assigned} assigned, {n_unassigned} unassigned")


def cmd_catalog_build(args: argparse.Namespace) -> None:
    """Build an album from the Choice Kit classification (best variant per track)."""
    from chak.catalog.builder import build_album_from_classification

    config = load_config(args.config)
    repo_root = config.project_root.parent
    choicekit_dir = repo_root / "THE_CHAK_CHAK_MAGE_CHOICE_KIT"

    if args.choicekit:
        choicekit_dir = Path(args.choicekit)

    album = build_album_from_classification(
        choicekit_dir=choicekit_dir,
        album_id=args.album_id,
        title=args.title or f"The Chak Chak Mage - {args.album_id}",
        project_root=config.project_root,
        track_names=config.tracks.names,
        track_titles=config.tracks.titles,
        copy_audio=True,
    )
    print(f"Built album: {album.album_id} with {len(album.tracks)} tracks")


def cmd_catalog_status(args: argparse.Namespace) -> None:
    """Show Choice Kit / catalog status."""
    config = load_config(args.config)
    repo_root = config.project_root.parent
    choicekit_dir = repo_root / "THE_CHAK_CHAK_MAGE_CHOICE_KIT"

    if args.choicekit:
        choicekit_dir = Path(args.choicekit)

    raw_dir = choicekit_dir / "RAW"
    raw_alignment = raw_dir / "alignment"

    print(f"Choice Kit: {choicekit_dir}")

    # RAW files
    if raw_dir.is_dir():
        mp3s = [f for f in raw_dir.iterdir() if f.suffix.lower() == ".mp3"]
        print(f"  RAW MP3s: {len(mp3s)}")
    else:
        print("  RAW/: NOT FOUND")

    # RAW index
    idx = choicekit_dir / "RAW_index.json"
    print(f"  RAW_index.json: {'EXISTS' if idx.exists() else 'MISSING'}")

    # Alignment
    if raw_alignment.is_dir():
        aligns = [f for f in raw_alignment.iterdir() if f.suffix == ".json"]
        print(f"  RAW alignments: {len(aligns)}")
    else:
        print(f"  RAW/alignment/: NOT FOUND")

    # Classification
    report = choicekit_dir / "classification_report.json"
    if report.exists():
        from chak.utils.io import load_json
        data = load_json(report)
        assigned = data.get("assigned", [])
        unassigned = data.get("unassigned", [])
        print(f"  Classification: {len(assigned)} assigned, {len(unassigned)} unassigned")
    else:
        print("  classification_report.json: MISSING")

    # Track folders
    track_dirs = sorted(
        d for d in choicekit_dir.iterdir()
        if d.is_dir() and d.name.upper().startswith("TRACK_")
    )
    for td in track_dirs:
        mp3s = [f for f in td.iterdir() if f.suffix.lower() == ".mp3"]
        print(f"  {td.name}: {len(mp3s)} variants")


def cmd_beats(args: argparse.Namespace) -> None:
    """Detect musical beats for album tracks."""
    from chak.utils.beats import detect_album_beats

    config = load_config(args.config)
    album_dir = config.project_root / "albums" / args.album_id
    results = detect_album_beats(album_dir)
    for tid, beats in results.items():
        print(f"  {tid}: {len(beats)} beats")
    print(f"Beat detection complete: {len(results)} tracks")


def cmd_structure(args: argparse.Namespace) -> None:
    """Analyze musical structure for album tracks."""
    from chak.utils.structure import analyze_album_tracks

    config = load_config(args.config)
    album_dir = config.project_root / "albums" / args.album_id
    results = analyze_album_tracks(album_dir)
    for tid, s in results.items():
        print(f"  {tid}: {len(s['sections'])} sections, {s['bpm']:.0f} BPM, {len(s['transition_points'])} transitions")
    print(f"Structure analysis complete: {len(results)} tracks")


def cmd_expand_prompts(args: argparse.Namespace) -> None:
    """Expand media_queries to 3 per line using Ollama."""
    from chak.tools.expand_prompts import expand_semantic_prompts

    config = load_config(args.config)
    matrix_path = config.project_root / "shared" / "semantics" / "base_semantic_matrix.json"
    stats = expand_semantic_prompts(matrix_path, dry_run=args.dry_run)
    total = sum(stats.values())
    print(f"Expanded {total} lines across {len(stats)} tracks")
    for tid, count in stats.items():
        print(f"  {tid}: {count} lines")


def cmd_status(args: argparse.Namespace) -> None:
    """Show pipeline status for an album."""
    config = load_config(args.config)
    album_dir = config.project_root / "albums" / args.album_id

    if not album_dir.exists():
        print(f"Album directory not found: {album_dir}")
        sys.exit(1)

    alignment_dir = album_dir.parent / "alignment"
    has_alignment = alignment_dir.is_dir() and any(alignment_dir.glob("track_*_words.json"))

    checks = {
        "album_config.json": (album_dir / "album_config.json").exists(),
        "semantic_matrix.json": (album_dir / "semantic_matrix.json").exists(),
        "alignment data": has_alignment,
        "data/ (timelines)": any((album_dir / "data").glob("*.timeline.json")) if (album_dir / "data").exists() else False,
        "data/ (track JS)": any((album_dir / "data").glob("*.js")) if (album_dir / "data").exists() else False,
        "media_manifest.json": (album_dir / "media_manifest.json").exists(),
        "media/ (images)": any((album_dir / "media").glob("*.*")) if (album_dir / "media").exists() else False,
    }

    print(f"Album: {args.album_id}")
    for check, ok in checks.items():
        status = "OK" if ok else "MISSING"
        print(f"  [{status:7s}] {check}")


def main() -> None:
    _setup_logging()

    parser = argparse.ArgumentParser(
        prog="chak",
        description="The Chak Chak Mage — Interactive Album Pipeline",
    )
    parser.add_argument("--config", type=str, default=None, help="Path to chak_pipeline.toml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── catalog commands ──
    p_cat = subparsers.add_parser("catalog", help="Catalog management (extract/align/classify)")
    p_cat.add_argument("--choicekit", type=str, help="Path to Choice Kit directory")
    p_cat.set_defaults(func=cmd_catalog)
    cat_sub = p_cat.add_subparsers(dest="catalog_command", required=True)

    # catalog extract
    p_cat_ext = cat_sub.add_parser("extract", help="Extract MP3s from archive zips")
    p_cat_ext.add_argument("--zips", nargs="+", required=True, help="Zip file paths")
    p_cat_ext.set_defaults(catalog_func=cmd_catalog_extract)

    # catalog align-raw
    p_cat_align = cat_sub.add_parser("align-raw", help="Align RAW MP3s with Whisper")
    p_cat_align.add_argument("--limit", type=int, default=0, help="Max files (0=all)")
    p_cat_align.add_argument("--force", action="store_true", help="Re-align existing")
    p_cat_align.set_defaults(catalog_func=cmd_catalog_align_raw)

    # catalog classify
    p_cat_cls = cat_sub.add_parser("classify", help="Classify aligned files to tracks")
    p_cat_cls.add_argument("--min-score", type=float, default=0.05)
    p_cat_cls.add_argument("--min-margin", type=float, default=0.01)
    p_cat_cls.add_argument("--high-score", type=float, default=0.45)
    p_cat_cls.add_argument("--clear-tracks", action="store_true", help="Clear existing TRACK_* folders")
    p_cat_cls.set_defaults(catalog_func=cmd_catalog_classify)

    # catalog build
    p_cat_build = cat_sub.add_parser("build", help="Build album from classification")
    p_cat_build.add_argument("album_id", help="Album ID to create")
    p_cat_build.add_argument("--title", type=str, help="Album title")
    p_cat_build.set_defaults(catalog_func=cmd_catalog_build)

    # catalog status
    p_cat_status = cat_sub.add_parser("status", help="Show catalog status")
    p_cat_status.set_defaults(catalog_func=cmd_catalog_status)

    # ── album build commands ──

    # build
    p_build = subparsers.add_parser("build", help="Build a single album")
    p_build.add_argument("album_id", nargs="?", help="Album ID")
    p_build.add_argument("--from-catalog", action="store_true", help="Build from Choice Kit selection")
    p_build.add_argument("--selected", type=str, help="Path to selected_album.json")
    p_build.add_argument("--mapping", type=str, help="Path to catalog_mapping.json")
    p_build.add_argument("--skip-alignment", action="store_true", help="Skip Whisper alignment")
    p_build.add_argument("--skip-media", action="store_true", help="Skip media fetching")
    p_build.add_argument("--reset-failed", action="store_true", help="Reset failed media concepts")
    p_build.set_defaults(func=cmd_build)

    # build-all
    p_all = subparsers.add_parser("build-all", help="Rebuild all albums")
    p_all.set_defaults(func=cmd_build_all)

    # align
    p_align = subparsers.add_parser("align", help="Run alignment only")
    p_align.add_argument("album_id", help="Album ID")
    p_align.add_argument("--track", type=str, help="Single track ID")
    p_align.set_defaults(func=cmd_align)

    # timeline
    p_tl = subparsers.add_parser("timeline", help="Build timelines only")
    p_tl.add_argument("album_id", help="Album ID")
    p_tl.add_argument("--track", type=str, help="Single track ID")
    p_tl.set_defaults(func=cmd_timeline)

    # media-prep
    p_mp = subparsers.add_parser("media-prep", help="Prepare media manifest only")
    p_mp.add_argument("album_id", help="Album ID")
    p_mp.set_defaults(func=cmd_media_prep)

    # media-fetch
    p_mf = subparsers.add_parser("media-fetch", help="Fetch media images only")
    p_mf.add_argument("album_id", help="Album ID")
    p_mf.add_argument("--reset-failed", action="store_true", help="Reset failed concepts")
    p_mf.add_argument("--reset-placeholders", action="store_true", help="Re-fetch SVG placeholders with real images")
    p_mf.add_argument("--max-requests", type=int, help="Max network requests")
    p_mf.add_argument("--seed-dir", type=str, help="Seed directory for pre-existing images")
    p_mf.set_defaults(func=cmd_media_fetch)

    # fuse
    p_fuse = subparsers.add_parser("fuse", help="Run fusion only")
    p_fuse.add_argument("album_id", help="Album ID")
    p_fuse.add_argument("--track", type=str, help="Single track ID")
    p_fuse.set_defaults(func=cmd_fuse)

    # export
    p_export = subparsers.add_parser("export", help="Run JS export only")
    p_export.add_argument("album_id", help="Album ID")
    p_export.set_defaults(func=cmd_export)

    # validate
    p_val = subparsers.add_parser("validate", help="Validate album data")
    p_val.add_argument("album_id", help="Album ID")
    p_val.set_defaults(func=cmd_validate)

    # index
    p_idx = subparsers.add_parser("index", help="Regenerate albums index")
    p_idx.set_defaults(func=cmd_index)

    # beats
    p_beats = subparsers.add_parser("beats", help="Detect musical beats for album tracks")
    p_beats.add_argument("album_id", help="Album ID")
    p_beats.set_defaults(func=cmd_beats)

    # structure
    p_struct = subparsers.add_parser("structure", help="Analyze musical structure for album tracks")
    p_struct.add_argument("album_id", help="Album ID")
    p_struct.set_defaults(func=cmd_structure)

    # expand-prompts
    p_expand = subparsers.add_parser("expand-prompts", help="Expand media prompts to 3 per line (Ollama)")
    p_expand.add_argument("--dry-run", action="store_true", help="Don't actually call Ollama or write")
    p_expand.set_defaults(func=cmd_expand_prompts)

    # status
    p_status = subparsers.add_parser("status", help="Show album pipeline status")
    p_status.add_argument("album_id", help="Album ID")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
