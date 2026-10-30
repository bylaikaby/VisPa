"""Safe command-line entry point; data acquisition requires explicit configuration.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../../CHANGELOG.md
"""
from .commands import main

if __name__ == "__main__":
    raise SystemExit(main())
