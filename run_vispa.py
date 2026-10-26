"""Launch the VisPa GUI from this checkout.

The installed commands are `vispa` and `python -m vispa`. This script remains
the checkout shortcut: with no arguments it opens the GUI, and any other
arguments are passed through to that same CLI.

Version: 1.11.0.dev17 (local/unreleased)
Last updated: 2026-10-27
Change history: CHANGELOG.md
"""
from pathlib import Path
import sys


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from vispa.cli import main

    raise SystemExit(main(sys.argv[1:] or ["gui"]))
