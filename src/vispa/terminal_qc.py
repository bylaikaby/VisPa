"""Compatibility alias for SWC terminal candidate tables.

Version: 1.20.1 (local/unreleased)
Last updated: 2026-11-04
Change history: ../../CHANGELOG.md
"""
import sys
from . import swc_terminal_candidates as _implementation

sys.modules[__name__] = _implementation
