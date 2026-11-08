"""Compatibility entry point for the packaged review bulk renderer.

Version: 1.21.0 (local/unreleased)
Last updated: 2026-11-08
Change history: ../CHANGELOG.md
"""
import sys
from vispa import review_bulk_render as _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
sys.modules[__name__] = _impl
