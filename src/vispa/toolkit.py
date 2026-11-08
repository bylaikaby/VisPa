"""Compatibility alias for the microscopy panel renderer.

Version: 1.21.0 (local/unreleased)
Last updated: 2026-11-08
Change history: ../../CHANGELOG.md
"""
import sys
from .renderers import microscopy_panels as _implementation

sys.modules[__name__] = _implementation
