"""Safe command-line entry point; data acquisition requires explicit configuration.

Version: 1.20.2 (local/unreleased)
Last updated: 2026-11-07
Change history: ../../CHANGELOG.md
"""
from .commands import main

if __name__ == "__main__":
    raise SystemExit(main())
