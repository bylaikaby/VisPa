"""Compatibility alias for consolidated vispa.config.

Version: 1.20.2 (local/unreleased)
Last updated: 2026-11-07
Change history: ../../CHANGELOG.md
"""
import sys
from . import config as _config
sys.modules[__name__] = _config

if __name__ == "__main__":
    raise SystemExit(_config.main())
