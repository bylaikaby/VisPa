"""Compatibility alias for the microscopy panel renderer.

Version: 1.20.2 (local/unreleased)
Last updated: 2026-11-07
Change history: ../../CHANGELOG.md
"""
import sys
from .renderers import microscopy_panels as _implementation

sys.modules[__name__] = _implementation
