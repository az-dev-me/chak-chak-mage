"""Extract raw MP3 files from archive zip files into Choice Kit RAW/.

Handles deduplication by file size: if same filename already exists with
identical size, skip it; if different size, suffix with __2, __3, etc.

Ported from pipeline/raw_catalog_extract.py.
"""

from __future__ import annotations

import logging
import os
import shutil
import zipfile
from pathlib import Path

from chak.utils.io import ensure_dir, write_json

logger = logging.getLogger(__name__)


def extract_zips_to_raw(
    zip_paths: list[str | Path],
    raw_dir: Path,
) -> list[dict]:
    """Extract all MP3 files from zip archives into raw_dir.

    Returns an index list with {name, raw_path, source_zip, size, deduped}.
    """
    ensure_dir(raw_dir)
    index: list[dict] = []

    for zip_path in zip_paths:
        zp = Path(zip_path).resolve()
        if not zp.exists():
            logger.warning("Zip not found: %s (skipping)", zp)
            continue

        logger.info("Reading zip: %s", zp)
        with zipfile.ZipFile(zp, "r") as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                name = info.filename.replace("\\", "/")
                base = os.path.basename(name)
                if not base.lower().endswith(".mp3"):
                    continue

                dest = raw_dir / base
                final_dest = dest

                if dest.exists():
                    existing_size = dest.stat().st_size
                    if existing_size == info.file_size:
                        # Assume identical by size — skip
                        index.append({
                            "name": base,
                            "raw_path": str(final_dest),
                            "source_zip": str(zp),
                            "size": info.file_size,
                            "deduped": True,
                        })
                        continue

                    # Different size — suffix to make unique
                    stem = dest.stem
                    ext = dest.suffix
                    k = 2
                    while True:
                        candidate = raw_dir / f"{stem}__{k}{ext}"
                        if not candidate.exists():
                            final_dest = candidate
                            break
                        k += 1

                logger.info("Extracting %s -> %s", base, final_dest.name)
                with z.open(info, "r") as src, open(final_dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)

                index.append({
                    "name": final_dest.name,
                    "raw_path": str(final_dest),
                    "source_zip": str(zp),
                    "size": info.file_size,
                    "deduped": False,
                })

    return index


def extract_and_index(
    zip_paths: list[str | Path],
    choicekit_dir: Path,
    repo_root: Path,
) -> list[dict]:
    """Extract zips to RAW/ and write RAW_index.json.

    Returns the index entries.
    """
    raw_dir = choicekit_dir / "RAW"
    ensure_dir(choicekit_dir)
    ensure_dir(raw_dir)

    raw_index = extract_zips_to_raw(zip_paths, raw_dir)

    # Normalize paths to repo-relative forward-slash for portability
    out = []
    for entry in raw_index:
        try:
            rel = os.path.relpath(entry["raw_path"], repo_root).replace("\\", "/")
        except ValueError:
            rel = entry["raw_path"]
        out.append({
            "name": entry["name"],
            "raw_path": rel,
            "source_zip": entry["source_zip"],
            "size": entry["size"],
            "deduped": entry["deduped"],
        })

    index_path = choicekit_dir / "RAW_index.json"
    write_json(index_path, out)
    logger.info("Wrote RAW_index.json -> %s (%d MP3 entries)", index_path, len(out))

    return out
