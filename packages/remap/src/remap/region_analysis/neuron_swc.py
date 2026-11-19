"""One SWC: load the graph and draw its shape.

``NeuronTracer`` is the single-neuron unit. It reads SWC text or the configured
cache, fetches from IONData only when the file is missing or refresh is set,
and divides XYZ by 250 for the atlas step. ``plot_neuron`` draws that graph.
Population analysis calls this unit once per neuron.

Version: 0.1.0.dev28 (local/unreleased)
Last updated: 2026-11-10
Change history:
- 2026-11-10: NeuronTracer moved here as the single-neuron load and shape-plot unit.
Status: candidate
"""
from __future__ import annotations

from pathlib import Path


class Node:
    def __init__(self, row):
        self.id, self.type = int(row[0]), int(row[1])
        self.x, self.y, self.z = map(float, row[2:5])
        self.radius, self.parent = float(row[5]), int(row[6])
        self.children = []
        self.is_terminal = False
        self.order = 0


class NeuronTracer:
    """Read one SWC from text, a file, or the configured cache."""

    def __init__(self):
        self.swc_filename = None
        self.nodes = {}
        self.root = None
        self.branches = []
        self.terminal_nodes = []
        self.outliers = []

    def process(self, exp_no, swc_filename, nii_space="monkey", swc=None,
                cache_root=None, iondata_host=None, allow_download=True,
                refresh=False, opener=None):
        if swc is None and cache_root is not None:
            from .neuron_loader import ensure_cached_swc
            swc = ensure_cached_swc(exp_no, swc_filename, cache_root, iondata_host,
                                    allow_download=allow_download or refresh,
                                    refresh=refresh, opener=opener)
        if swc is None:
            raise FileNotFoundError(f"SWC is not in the cache: {exp_no}/{swc_filename}")
        path = Path(swc) if isinstance(swc, (str, Path)) else None
        try:
            local_file = path is not None and path.is_file()
        except (OSError, ValueError):
            local_file = False
        if local_file:
            if path.name != swc_filename:
                raise ValueError("Cached SWC filename must match the neuron id")
            contents = path.read_text(encoding="utf-8-sig")
        elif isinstance(swc, str) and len(swc.split()) >= 7:
            contents = swc
        else:
            raise ValueError("SWC must be a cache file or SWC text")
        if nii_space != "monkey":
            raise ValueError("Full population workflow currently requires explicit monkey /250 voxel mapping")
        from .neuron_table import parse_swc
        rows = parse_swc(contents, source=str(path) if path else f"processed {exp_no}/{swc_filename}")
        self.nodes = {row[0]: Node(row) for row in rows}
        self.root = next(node for node in self.nodes.values() if node.parent == -1)
        self.swc_filename = swc_filename
        self.exp_no = exp_no
        for node in self.nodes.values():
            node.x_nii, node.y_nii, node.z_nii = node.x / 250, node.y / 250, node.z / 250
        for node in self.nodes.values():
            if node.parent != -1:
                self.nodes[node.parent].children.append(node)
        self.terminal_nodes = []
        for node in self.nodes.values():
            node.is_terminal = not node.children
            if node.is_terminal:
                self.terminal_nodes.append(node)
        self.branches = []
        pending = [(self.root, 0, None)]
        while pending:
            current, order, branch = pending.pop()
            branch = [current] if branch is None else branch
            current.order = order
            while len(current.children) == 1:
                current = current.children[0]
                current.order = order
                branch.append(current)
            if not current.children:
                self.branches.append(branch[:])
            else:
                if len(branch) > 1:
                    self.branches.append(branch[:])
                for child in reversed(current.children):
                    pending.append((child, order + 1, [current, child]))
        return self

    def plot_neuron(self, save_path=None, show: bool = True, space: str = "source", dpi: int = 300):
        """Legacy 3D SWC shape plot: nodes by branch order, terminals, soma.

        ``space`` is ``source`` (stored XYZ) or ``nii`` (XYZ / 250). Does not
        claim anatomical acceptance or deformometry.
        """
        if not self.nodes or self.root is None:
            raise ValueError("Call process() before plot_neuron()")
        if space not in {"source", "nii"}:
            raise ValueError("space must be 'source' or 'nii'")
        import matplotlib.pyplot as plt

        xs, ys, zs, orders = [], [], [], []
        for node in self.nodes.values():
            if space == "nii":
                xs.append(node.x_nii)
                ys.append(node.y_nii)
                zs.append(node.z_nii)
            else:
                xs.append(node.x)
                ys.append(node.y)
                zs.append(node.z)
            orders.append(node.order)

        fig = plt.figure(figsize=(12, 8))
        ax = fig.add_subplot(111, projection="3d")
        scatter = ax.scatter(xs, ys, zs, c=orders, s=3, cmap="tab20", alpha=0.8)
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label("Order")

        if self.terminal_nodes:
            if space == "nii":
                tx = [n.x_nii for n in self.terminal_nodes]
                ty = [n.y_nii for n in self.terminal_nodes]
                tz = [n.z_nii for n in self.terminal_nodes]
            else:
                tx = [n.x for n in self.terminal_nodes]
                ty = [n.y for n in self.terminal_nodes]
                tz = [n.z for n in self.terminal_nodes]
            ax.scatter(tx, ty, tz, s=20, marker="*", color="black", label="Terminal Nodes")

        soma = self.root
        sx, sy, sz = ((soma.x_nii, soma.y_nii, soma.z_nii) if space == "nii"
                      else (soma.x, soma.y, soma.z))
        ax.scatter([sx], [sy], [sz], s=50, color="red", edgecolor="orange",
                   linewidth=1, marker="X", label="Soma")
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_zlabel("Z")
        ax.set_title(f"3D Single Neuron Plot - {self.swc_filename}")
        ax.legend()
        if save_path:
            kwargs = {"dpi": dpi, "bbox_inches": "tight"}
            if not isinstance(save_path, (str, Path)):
                kwargs["format"] = "png"
            fig.savefig(save_path, **kwargs)
            if isinstance(save_path, (str, Path)):
                print(f"[SAVED] {save_path}")
        if show:
            plt.show()
        else:
            plt.close(fig)
        return fig
