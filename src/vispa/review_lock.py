"""Compatibility alias for the VisPa batch run lock.

Version: 1.20.0 (local/unreleased)
Last updated: 2026-11-04
Change history: ../../CHANGELOG.md
"""
import sys
from . import batch_run_lock as _implementation

sys.modules[__name__] = _implementation
