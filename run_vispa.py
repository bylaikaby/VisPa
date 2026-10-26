"""Launch VisPa from this checkout.

Version: 1.11.0.dev15 (local/unreleased)
Last updated: 2026-10-26
Change history: CHANGELOG.md
"""
from pathlib import Path
import sys


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from vispa.cli import main

    raise SystemExit(main(sys.argv[1:] or ["gui"]))
