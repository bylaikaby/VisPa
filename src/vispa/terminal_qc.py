"""Compatibility alias for SWC terminal candidate tables.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../../CHANGELOG.md
"""
import sys
from . import swc_terminal_candidates as _implementation

sys.modules[__name__] = _implementation
