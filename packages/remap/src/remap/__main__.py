"""ReMAP python -m compatibility entry point.

Version: 0.1.0.dev8 (local/unreleased)
Last updated: 2026-10-29
Change history:
- 2026-10-29: python -m remap calls cli.main.
Status: candidate
"""
from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
