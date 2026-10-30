"""Compatibility alias for native FNT preparation and launch.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../../CHANGELOG.md
"""
import sys
from . import fnt_tracer_launcher as _implementation

sys.modules[__name__] = _implementation
