"""File I/O helpers with proper error handling."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> Any:
    """Load and parse a JSON file with a clear error on failure."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: str | Path, data: Any, *, indent: int = 4) -> None:
    """Write data as JSON, creating parent directories as needed."""
    path = Path(path)
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def ensure_dir(path: str | Path) -> Path:
    """Create directory (and parents) if it doesn't exist. Returns the Path."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_project_root(from_path: str | Path | None = None) -> Path:
    """Find THE_CHAK_CHAK_MAGE_INTERACTIVE_ALBUM root directory.

    Walks up from *from_path* (default: this file) looking for the
    ``chak_pipeline.toml`` marker file.
    """
    start = Path(from_path) if from_path else Path(__file__)
    current = start.resolve()

    for parent in [current] + list(current.parents):
        if (parent / "chak_pipeline.toml").exists():
            return parent

    # Fallback: assume we're in src/chak/utils/ → go up 3 levels
    return Path(__file__).resolve().parent.parent.parent.parent
