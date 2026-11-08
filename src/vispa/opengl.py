"""Compatibility entry point for SWC Brain View.

Version: 1.21.0 (local/unreleased)
Last updated: 2026-11-08
Change history: ../../CHANGELOG.md
"""
import sys
from .renderers import swc_brain_view as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
sys.modules[__name__] = _implementation
