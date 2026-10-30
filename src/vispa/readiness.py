"""Compatibility alias for input-resource checks.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../../CHANGELOG.md
"""
import sys
from . import input_resource_check as _implementation

sys.modules[__name__] = _implementation
