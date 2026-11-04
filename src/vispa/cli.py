"""Compatibility entry point for the VisPa review command line.

Version: 1.20.0 (local/unreleased)
Last updated: 2026-11-04
Change history: ../../CHANGELOG.md
"""
import sys
from . import commands as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
sys.modules[__name__] = _implementation
