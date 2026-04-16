#!/usr/bin/env python3
"""Compatibility wrapper for the generic YouTube batch pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from youtube_batch import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
