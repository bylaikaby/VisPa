"""Compatibility alias for input-resource checks.

Version: 1.20.0 (local/unreleased)
Last updated: 2026-11-04
Change history: ../../CHANGELOG.md
"""
import sys
from . import input_resource_check as _implementation

sys.modules[__name__] = _implementation
