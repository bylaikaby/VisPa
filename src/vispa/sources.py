"""Compatibility alias for :mod:`vispa.data_input_adaptor`.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../../CHANGELOG.md
"""
import sys
from . import data_input_adaptor as _adaptor

sys.modules[__name__] = _adaptor
