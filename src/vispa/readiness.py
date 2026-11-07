"""Compatibility alias for input-resource checks.

Version: 1.20.2 (local/unreleased)
Last updated: 2026-11-07
Change history: ../../CHANGELOG.md
"""
import sys
from . import input_resource_check as _implementation

sys.modules[__name__] = _implementation
