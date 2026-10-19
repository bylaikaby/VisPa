"""Safe command-line entry point; data acquisition requires explicit configuration.

Version: 1.10.0.dev0 (local/unreleased)
Last updated: 2026-10-18
Change history: ../../CHANGELOG.md
"""
from .cli import main

raise SystemExit(main())
