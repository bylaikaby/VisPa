"""Compatibility entry point for the VisPa review GUI.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../../CHANGELOG.md
"""
import sys
from . import reviewer as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
sys.modules[__name__] = _implementation
