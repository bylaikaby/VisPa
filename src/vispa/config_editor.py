"""Compatibility alias for consolidated vispa.config.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../../CHANGELOG.md
"""
import sys
from . import config as _config
sys.modules[__name__] = _config

if __name__ == "__main__":
    raise SystemExit(_config.main())
