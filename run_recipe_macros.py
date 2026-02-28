#!/usr/bin/env python3
"""Backward-compatible entrypoint for recipe macro generation CLI."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from recipe_macros.cli import main


if __name__ == "__main__":
    main()
