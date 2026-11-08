"""Launch VisPa from this checkout.

Version: 1.21.1 (local/unreleased)
Last updated: 2026-11-08
Change history: CHANGELOG.md
"""
from pathlib import Path
import sys


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from vispa.commands import main

    raise SystemExit(main(sys.argv[1:] or ["gui"]))
