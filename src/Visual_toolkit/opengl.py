"""Legacy import compatibility for VisPa.

Version: 1.11.0.dev3 (local/unreleased)
Last updated: 2026-10-22
Change history: ../../CHANGELOG.md
"""
import importlib,sys
if __name__ == "__main__":
    import runpy
    runpy.run_module('vispa.opengl',run_name="__main__")
else:
    sys.modules[__name__] = importlib.import_module('vispa.opengl')
