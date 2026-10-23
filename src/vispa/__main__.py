"""Safe command-line entry point; data acquisition requires explicit configuration.

Version: 1.11.0.dev9 (local/unreleased)
Last updated: 2026-10-23
Change history: ../../CHANGELOG.md
"""
from .cli import main

raise SystemExit(main())
