"""Safe command-line entry point; data acquisition requires explicit configuration.

Version: 1.11.0.dev1 (local/unreleased)
Last updated: 2026-10-22
Change history: ../../CHANGELOG.md
"""
from .cli import main

raise SystemExit(main())
