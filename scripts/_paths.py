"""Ensure the FeatherFlap source tree is importable when running standalone scripts."""

from __future__ import annotations

import sys
from pathlib import Path


def add_project_src_to_path() -> None:
    """Prepend the repository's src directory to sys.path if needed."""

    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    src_str = str(src)
    if src.exists() and src_str not in sys.path:
        sys.path.insert(0, src_str)
