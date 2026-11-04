"""Compatibility alias for :mod:`vispa.data_input_adaptor`.

Version: 1.20.0 (local/unreleased)
Last updated: 2026-11-04
Change history: ../../CHANGELOG.md
"""
import sys
from . import data_input_adaptor as _adaptor

sys.modules[__name__] = _adaptor
