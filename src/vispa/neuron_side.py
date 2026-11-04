"""Compatibility alias for neuron-side acquisition in data_input_adaptor.

Version: 1.20.1 (local/unreleased)
Last updated: 2026-11-04
Change history: ../../CHANGELOG.md
"""
import sys
from . import data_input_adaptor as _implementation

sys.modules[__name__] = _implementation
