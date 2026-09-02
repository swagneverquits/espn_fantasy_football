#!/usr/bin/env python3
"""Launch the fantasy football command-line interface."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fantasy_football.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
