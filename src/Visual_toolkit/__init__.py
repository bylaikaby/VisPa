"""Legacy import compatibility for VisPa.

Version: 1.11.0.dev1 (local/unreleased)
Last updated: 2026-10-22
Change history: ../../CHANGELOG.md
"""
from vispa import __version__
import vispa as _primary
def __getattr__(name): return getattr(_primary,name)
def __dir__(): return dir(_primary)
