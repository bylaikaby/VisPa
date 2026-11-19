"""Launch VisPa from this checkout.

Version: 1.21.8.dev1 (local/unreleased)
Last updated: 2026-11-18
Change history: CHANGELOG.md
2026-11-18: make the integrated ReMAP source available to the checkout launcher.
"""
from pathlib import Path
import sys


if __name__ == "__main__":
    checkout = Path(__file__).resolve().parent
    remap_src = checkout / "packages" / "remap" / "src"
    if remap_src.is_dir():
        sys.path.insert(0, str(remap_src))
    sys.path.insert(0, str(checkout / "src"))
    from vispa.commands import main

    raise SystemExit(main(sys.argv[1:] or ["gui"]))
