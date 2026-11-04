"""Compatibility alias for native FNT preparation and launch.

Version: 1.20.1 (local/unreleased)
Last updated: 2026-11-04
Change history: ../../CHANGELOG.md
"""
import sys
from . import fnt_tracer_launcher as _implementation

sys.modules[__name__] = _implementation
