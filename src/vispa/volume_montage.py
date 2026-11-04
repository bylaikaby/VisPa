"""Compatibility alias for the brain-volume montage renderer.

Version: 1.20.1 (local/unreleased)
Last updated: 2026-11-04
Change history: ../../CHANGELOG.md
"""
import sys
from .renderers import brain_volume_montage as _implementation

sys.modules[__name__] = _implementation
