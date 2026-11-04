"""Safe command-line entry point; data acquisition requires explicit configuration.

Version: 1.20.1 (local/unreleased)
Last updated: 2026-11-04
Change history: ../../CHANGELOG.md
"""
from .commands import main

if __name__ == "__main__":
    raise SystemExit(main())
