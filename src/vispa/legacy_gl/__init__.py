"""Optional faithful legacy OpenGL renderer.

Version: 1.11.0.dev2 (local/unreleased)
Last updated: 2026-10-22
Change history: ../../../CHANGELOG.md
Status: candidate

Imports stay lazy so the VisualToolkit core does not require OpenGL. Supply
explicit local root-mesh and processed-SWC paths; no provider, network access,
or coordinate transform is inferred.
"""
__all__ = ["RenderGL", "GeometryAdapter"]
def __getattr__(name):
    if name == "RenderGL":
        from .RenderGL import RenderGL
        return RenderGL
    if name == "GeometryAdapter":
        from .GeometryAdapter import GeometryAdapter
        return GeometryAdapter
    raise AttributeError(name)
