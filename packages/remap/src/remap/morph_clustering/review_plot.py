"""Profile-driven legacy-compatible FNT/type/projection review.
Version: 0.1.14 (local/unreleased)
Last updated: 2026-11-19
Change history: ../../../CHANGELOG.md
- 2026-11-19: Add an atlas-insula display of the saved hierarchy with the parent projection scale.
- 2026-11-19: Group the three hierarchy keys inside one compact, framed panel.
- 2026-11-19: Label the hierarchy legend rows and show observed annotation counts.
- 2026-11-18: Align cluster-colored dendrogram branches with a compact bilateral strength matrix.
- 2026-11-18: Add neuron-level projection distributions for existing candidate assignments.
- 2026-11-18: Add selectable dendrogram, distance matrix, and cluster projection styles.
- 2026-11-18: Separate crowded cluster labels and provide room between plot rows.
- 2026-11-18: Separate morphology examples into square panels with external identity titles.
- 2026-11-18: Parameter trade-off and monkey composition figures, including normalized within-monkey counts.
- 2026-11-18: Reusable hash-bound medoid/farthest morphology panels with shared full extent and coordinate planes.
- 2026-11-18: Integrated diagnostics, unknown-policy sensitivity and source-workbook evolution under one completion receipt.
- 2026-11-18: Optional aligned monkey strip and declared animal palette for cohort review.
- 2026-11-18: Explicit sparse-zero column union; existing nonfinite cells still rejected.
- 2026-11-18: Expose DPI, region count and display cut overrides with resolved-profile receipts.
- 2026-11-18: Extract identity-bound legacy review rendering with explicit public settings.
Status: candidate
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, leaves_list
from .review_profile import load_profile, fit_profile
from .clustering_validation import read_fnt_distances, file_sha256

VERSION = "0.1.14"


def prepare_projection(ipsi, contra, identities, top_regions):
    """Align explicitly, normalize all regions, then select display columns."""
    for frame in (ipsi, contra):
        if not frame.index.is_unique or not frame.columns.is_unique:
            raise ValueError("Duplicate projection identity or region")
        if not set(identities).issubset(frame.index):
            raise ValueError("Missing projection identities")
    regions = sorted(set(ipsi.columns) | set(contra.columns))
    if type(top_regions) is not int or not 1 <= top_regions <= len(regions):
        raise ValueError("top_regions must fit available region columns")
    arrays = [f.loc[identities].reindex(columns=regions, fill_value=0).to_numpy(float)
              for f in (ipsi, contra)]
    both = np.concatenate(arrays, axis=1)
    if not np.isfinite(both).all() or np.any(both < 0) or np.any(both.sum(axis=1) <= 0):
        raise ValueError("Projection lengths must be finite/nonnegative with positive totals")
    fraction = both / both.sum(axis=1)[:, None]
    # Preserve the tested legacy operator's default argsort ordering, including ties.
    ranked = np.argsort(-(fraction[:, :len(regions)] + fraction[:, len(regions):]).mean(axis=0))[:top_regions]
    shown = np.concatenate([fraction[:, ranked], fraction[:, len(regions) + ranked]], axis=1)
    return shown, [regions[i] for i in ranked], fraction


def load_tables(spec, identities, level, missing_region_policy="error"):
    if missing_region_policy not in ("error", "sparse_zero"):
        raise ValueError("Unknown missing region policy")
    summaries, sides, sources = [], {"ipsi": [], "contra": []}, []
    if not isinstance(spec, list) or not spec:
        raise ValueError("Table specification must be a nonempty list")
    for entry in spec:
        if set(entry) != {"sample", "animal", "path"}:
            raise ValueError("Each table requires exact sample, animal and path fields")
        path = Path(entry["path"])
        sources.append({**entry, "sha256": file_sha256(path)})
        for sheet in ["Summary", *[f"Projection_Length_{level}_{s}" for s in sides]]:
            frame = pd.read_excel(path, sheet_name=sheet, dtype={"NeuronID": str})
            if frame.NeuronID.isna().any() or frame.NeuronID.duplicated().any():
                raise ValueError("Invalid or duplicated source neuron ID")
            frame.index = [str(entry["sample"]) + "_" + n.removesuffix(".swc") for n in frame.NeuronID]
            frame = frame.drop(columns="NeuronID")
            if sheet == "Summary":
                frame["SampleID"] = str(entry["sample"])
                frame["AnimalID"] = str(entry["animal"])
                summaries.append(frame)
            else:
                sides[sheet.rsplit("_", 1)[-1]].append(frame.drop(columns="Neuron_Type"))
    summary = pd.concat(summaries)
    if not summary.index.is_unique or not set(identities).issubset(summary.index):
        raise ValueError("Duplicate or missing composite identities in Summary")
    if missing_region_policy == "sparse_zero":
        # Exporter constructs columns only from observed nonzero regional lengths.
        # Never fill a missing cell within an existing source column.
        for side, frames in sides.items():
            columns = sorted(set().union(*(set(f.columns) for f in frames)))
            for frame in frames:
                values = frame.to_numpy(float)
                if not np.isfinite(values).all() or np.any(values < 0):
                    raise ValueError("Invalid cell within source projection columns")
            sides[side] = [f.reindex(columns=columns, fill_value=0) for f in frames]
    for source in sources:
        source["missing_region_policy"] = missing_region_policy
    return summary.loc[identities], {s: pd.concat(frames) for s, frames in sides.items()}, sources


def render_review(fits, types, identities, projection, regions, profile, output, title, animals=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, is_color_like
    from matplotlib.patches import Patch
    settings = profile["plots"]
    factors = settings.get("penalty_factors", [0, profile["clustering"]["penalty_factor"]])
    if not factors or len(factors) != len(set(factors)) or any(f not in fits for f in factors):
        raise ValueError("Plot penalties must uniquely reference fitted methods")
    palette = settings["type_palette"]
    if set(types) - set(palette) or any(not is_color_like(c) for c in palette.values()):
        raise ValueError("Every type needs a valid declared palette color")
    dpi = settings.get("dpi", 190)
    if type(dpi) is not int or not 72 <= dpi <= 600:
        raise ValueError("DPI must be 72..600")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    n, width = len(identities), len(regions)
    names = list(palette)
    animal_palette = settings.get("animal_palette", {})
    if animals is not None:
        if len(animals) != n or set(animals) - set(animal_palette):
            raise ValueError("Every aligned animal requires a declared color")
        if any(not is_color_like(c) for c in animal_palette.values()):
            raise ValueError("Invalid animal color")
    k = profile["clustering"]["display_k"]
    fig = plt.figure(figsize=(settings.get("width_inches", 17), 7.5 * len(factors)))
    gs = fig.add_gridspec(len(factors), 4, width_ratios=[1, .25 if animals is not None else .10, 3.5, 4],
                         left=.05, right=.94, bottom=.15, top=.87 if animals is not None else .91, wspace=.12, hspace=.60)
    orders = {}
    for row, factor in enumerate(factors):
        fit = fits[factor]
        order = leaves_list(fit["tree"])
        orders[str(factor)] = [identities[i] for i in order]
        axes = [fig.add_subplot(gs[row, c]) for c in range(4)]
        dendrogram(fit["tree"], orientation="left", no_labels=True, color_threshold=0,
                   above_threshold_color="#555555", ax=axes[0])
        axes[0].set_ylim(0, n * 10)
        axes[0].invert_yaxis()
        axes[0].set(xlabel="Ward height", title="Unguided" if factor == 0 else f"Type-guided ({factor:g} x max)")
        strip = np.array([names.index(t) for t in types])[:, None]
        colors = list(palette.values())
        if animals is not None:
            animal_names = list(animal_palette)
            strip = np.column_stack([strip[:, 0], [len(names)+animal_names.index(a) for a in animals]])
            colors += list(animal_palette.values())
        axes[1].imshow(strip[order], aspect="auto", interpolation="nearest",
                       cmap=ListedColormap(colors), vmin=-.5, vmax=len(colors)-.5)
        axes[1].set_xticks(range(strip.shape[1]), ["Type", "Monkey"][:strip.shape[1]], rotation=90)
        axes[1].set_yticks([])
        im = axes[2].imshow(fit["distance"][np.ix_(order, order)], aspect="auto", interpolation="nearest",
                            cmap="magma", vmin=0, vmax=max(v["distance"].max() for v in fits.values()))
        axes[2].set(title="Clustering distance (same scale)", xlabel="Neurons in dendrogram order")
        pr = axes[3].imshow(np.log10(1+100*projection[order]), aspect="auto", interpolation="nearest",
                            cmap="viridis", vmin=0, vmax=np.log10(101))
        axes[3].axvline(width-.5, color="white", lw=2)
        axes[3].set(title="Projection fraction of bilateral " + settings["projection_level"] + " total\nIpsilateral                         Contralateral", yticks=[])
        axes[3].set_xticks(range(width*2), regions*2, rotation=90, fontsize=7)
        labels = fit["cuts"][k][order]
        groups = list(dict.fromkeys(labels))
        # Place small-cluster labels apart and connect them to their true centers.
        centers = np.array([np.where(labels == c)[0].mean() for c in groups])
        locations = 1 - (centers + .5) / n
        spaced = np.clip(locations.copy(), .02, .98)
        for i in range(1, len(spaced)):
            spaced[i] = min(spaced[i], spaced[i - 1] - .035)
        if len(spaced) and spaced[-1] < .02:
            spaced += .02 - spaced[-1]
        axes[2].set_yticks([])
        for cluster, center, position in zip(groups, centers, spaced):
            axes[2].annotate(f"C{cluster}", xy=(0, center), xycoords=("axes fraction", "data"),
                             xytext=(-.035, position), textcoords="axes fraction",
                             ha="right", va="center", fontsize=7,
                             arrowprops={"arrowstyle": "-", "lw": .5, "color": "#555555"})
        for boundary in np.flatnonzero(labels[1:] != labels[:-1])+.5:
            axes[2].axvline(boundary, color="white", lw=.5, alpha=.7)
            for ax in axes[1:]:
                ax.axhline(boundary, color="white", lw=.5, alpha=.7)
    fig.colorbar(im, cax=fig.add_axes([.955,.57,.012,.25]), label="Distance incl. type penalty")
    cb = fig.colorbar(pr, cax=fig.add_axes([.955,.20,.012,.25]), label="Projection fraction (log display)")
    cb.set_ticks(np.log10(1+100*np.array([0,.01,.05,.1,.5,1])))
    cb.set_ticklabels(["0","1%","5%","10%","50%","100%"])
    fig.legend(handles=[Patch(color=palette[t], label=t) for t in names], loc="upper center",
               ncol=len(names), bbox_to_anchor=(.5,.965), frameon=False)
    if animals is not None:
        fig.legend(handles=[Patch(color=c, label=a) for a, c in animal_palette.items()], loc="upper center",
                   ncol=len(animal_palette), bbox_to_anchor=(.5,.94), frameon=False, fontsize=8)
    fig.suptitle(title, y=.995, fontsize=15)
    fig.text(.05,.025, f"White boundaries: k={k} candidate cut. Top {width} regions by mean bilateral fraction; normalization uses ALL regions.\n"
             "Type-guided fitting is not independent type validation. Projection values are existing atlas-table derivatives.", fontsize=9)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            fig.savefig(stream, format="png", dpi=dpi, bbox_inches="tight", pad_inches=.12)
    finally:
        plt.close(fig)
    return orders


def atlas_insula_display_ids(path, summary):
    """Bind the ARM L6 insula display roster to the loaded parent cohort."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    parcels = {"Ia/Id", "Iai", "Ial", "Iapl", "Ig"}
    expected = {name for name, region in summary.Soma_Region.items()
                if isinstance(region, str) and region.partition("_")[2] in parcels}
    cases = data["neurons"]
    atlas_ids = {row["neuron"] for row in cases}
    if (set(data["selection"]) != parcels or data["cohort_size"] != len(summary)
            or data["selected_size"] != len(cases) or len(atlas_ids) != len(cases) or atlas_ids != expected):
        raise ValueError("Atlas receipt must match the complete ARM L6 insula selection in the parent cohort")
    columns = {"soma_region": "Soma_Region", "soma_side": "Soma_Side",
               "neuron_type": "Neuron_Type", "animal": "AnimalID"}
    for row in cases:
        if any(str(summary.at[row["neuron"], source]) != str(row[target]) for target, source in columns.items()):
            raise ValueError(f"Atlas receipt annotation mismatch: {row['neuron']}")
    return [name for name in summary.index if name in atlas_ids]


def restrict_linkage(tree, selected):
    """Remove unshown leaves, retaining the original heights of surviving merges."""
    nodes = {int(old): (new, 1) for new, old in enumerate(selected)}
    original_size = len(tree) + 1
    rows = []
    for index, (left, right, height, _) in enumerate(tree, original_size):
        first, second = nodes.get(int(left)), nodes.get(int(right))
        if first is not None and second is not None:
            count = first[1] + second[1]
            nodes[index] = (len(selected) + len(rows), count)
            rows.append((first[0], second[0], height, count))
        elif first is not None or second is not None:
            nodes[index] = first if first is not None else second
    return np.asarray(rows, dtype=float)


def draw_hierarchy_key(fig, frame, sections):
    """Draw compact swatches and counts inside a single annotation panel."""
    from matplotlib.patches import Rectangle

    ax = fig.add_axes(frame, label="hierarchy annotation key")
    ax.set_axis_off()
    ax.add_patch(Rectangle((0, 0), 1, 1, facecolor="#f8fafb", edgecolor="#a7b4bd",
                           linewidth=.75, transform=ax.transAxes, clip_on=False))
    height_inches = frame[3] * fig.get_figheight()
    bounds = (0., .326, .685, 1.)
    for section, left, right in zip(sections, bounds[:-1], bounds[1:], strict=True):
        title, columns, entries = section
        if left:
            ax.plot([left, left], [.13, .87], color="#dce5e9", lw=.75, transform=ax.transAxes)
        ax.text(left + .014, 1 - .16 / height_inches, title, color="#192c38",
                fontsize=9.5, weight="bold", va="center", transform=ax.transAxes)
        cell_width = (right - left - .026) / columns
        for index, (name, color, count) in enumerate(entries):
            row, col = divmod(index, columns)
            x = left + .014 + col * cell_width
            y = 1 - (.36 + .20 * row) / height_inches
            swatch_height = .093 / height_inches
            ax.add_patch(Rectangle((x, y - swatch_height / 2), .012, swatch_height,
                                   facecolor=color, edgecolor="#7a8790", linewidth=.35,
                                   transform=ax.transAxes))
            ax.text(x + .019, y, name, fontsize=9, color="#192c38", va="center", transform=ax.transAxes)
            ax.text(x + cell_width - .009, y, f"n={count}", fontsize=8.5, color="#4b606c",
                    ha="right", va="center", transform=ax.transAxes)


def render_alternative(fit, types, animals, identities, projection, regions, profile,
                       output, style, prevalence_threshold=.01, dpi=None,
                       projection_lengths=None, length_unit="retained atlas-voxel length (source-table units)",
                       total_regions=None, atlas_insula_ids=None):
    """Render one declared style from an existing fit and normalized projections."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    if style not in ("neuron_projection", "distance_matrix", "cluster_summary"):
        raise ValueError("Unknown alternative review style")
    if atlas_insula_ids is not None and style != "neuron_projection":
        raise ValueError("Atlas insula display requires neuron_projection")
    if not 0 <= prevalence_threshold <= 1:
        raise ValueError("prevalence_threshold must be between zero and one")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    settings = profile["plots"]
    dpi = settings.get("dpi", 190) if dpi is None else dpi
    if type(dpi) is not int or not 72 <= dpi <= 600:
        raise ValueError("DPI must be 72..600")
    n, w = len(identities), len(regions)
    if len(types) != n or len(animals) != n or np.shape(projection) != (n, 2*w):
        raise ValueError("Annotation and projection rows must match identities")
    if (not np.isfinite(projection).all() or np.any(projection < 0)
            or np.any(np.sum(projection,axis=1) > 1 + 1e-9)):
        raise ValueError("Projection fractions must be finite, nonnegative, and sum to at most one per neuron")
    k = profile["clustering"]["display_k"]
    factor = profile["clustering"]["penalty_factor"]
    parent_n = n
    linkage = fit["tree"]
    labels = np.asarray(fit["cuts"][k])
    parent_groups = sorted(set(labels))
    if style == "neuron_projection":
        projection_lengths = np.asarray(projection_lengths, dtype=float)
        if (projection_lengths.shape != (n, 2*w) or not np.isfinite(projection_lengths).all()
                or np.any(projection_lengths < 0)):
            raise ValueError("Neuron projection style requires aligned nonnegative projection lengths")
        length_values = np.round(np.log10(1 + projection_lengths), 4)
        scale_max = max(float(length_values.max()), 1e-12)
    if atlas_insula_ids is not None:
        atlas_ids = set(atlas_insula_ids)
        if (len(set(identities)) != n or len(atlas_ids) != len(atlas_insula_ids)
                or len(atlas_ids) < 2 or not atlas_ids.issubset(identities)):
            raise ValueError("Atlas display requires two or more unique, matched cohort identities")
        selected = [i for i, identity in enumerate(identities) if identity in atlas_ids]
        linkage = restrict_linkage(linkage, selected)
        identities = [identities[i] for i in selected]
        types = [types[i] for i in selected]
        animals = [animals[i] for i in selected]
        labels, projection, length_values = labels[selected], np.asarray(projection)[selected], length_values[selected]
        n = len(identities)
    region_scope = f"Top {w}" + (f" of {total_regions}" if total_regions is not None else "") + " regions by mean bilateral fraction"
    if atlas_insula_ids is not None:
        region_scope += " in the parent cohort"
    retained_fraction = float(np.asarray(projection).sum(axis=1).mean())
    order = leaves_list(linkage)
    groups = sorted(set(labels)); type_palette = settings["type_palette"]
    animal_palette = settings["animal_palette"]
    if set(types) - set(type_palette) or set(animals) - set(animal_palette):
        raise ValueError("Missing type or animal palette color")
    cluster_palette = {c: plt.get_cmap("tab20")((i*2) % 20) for i, c in enumerate(parent_groups)}
    ordered_labels = labels[order]
    cluster_counts = {str(c): int(np.sum(labels == c)) for c in groups}
    legend = [Patch(color=type_palette[t], label=t) for t in type_palette]
    animal_legend = [Patch(color=animal_palette[a], label=a) for a in animal_palette]
    cluster_legend = [Patch(color=cluster_palette[c], label=f"C{c} (n={cluster_counts[str(c)]})") for c in groups]
    shown = np.log10(1 + 100 * projection[order])
    boundaries = np.flatnonzero(ordered_labels[1:] != ordered_labels[:-1]) + .5
    if style == "neuron_projection":
        from matplotlib.colors import to_hex
        type_counts, animal_counts = Counter(types), Counter(animals)
        sections = (
            ("Neuron type", 2, [(t, c, type_counts[t]) for t, c in type_palette.items() if t in type_counts]),
            ("Animal ID", 3, [(a, c, animal_counts[a]) for a, c in animal_palette.items() if a in animal_counts]),
            ("Candidate cluster", 3, [(f"C{c}", cluster_palette[c], cluster_counts[str(c)]) for c in groups]),
        )
        key_rows = max((len(entries) + columns - 1) // columns for _, columns, entries in sections)
        key_inches = .50 + .20 * (key_rows - 1)
        figure_height = max(8, 4.1 + w * .28) + max(0, key_rows - 3) * .20 + .22
        fig = plt.figure(figsize=(16, figure_height))
        key_height = key_inches / figure_height
        key_bottom = .926 - key_height
        gs = fig.add_gridspec(4, 2, height_ratios=[2.2, .65, 2.4, 2.4],
                              width_ratios=[44, 1], left=.14, right=.92,
                              bottom=.10, top=key_bottom - .026, hspace=.19, wspace=.035)
        tree = fig.add_subplot(gs[0, 0])
        band = fig.add_subplot(gs[1, 0])
        axes = [fig.add_subplot(gs[i, 0]) for i in (2, 3)]
        cax = fig.add_subplot(gs[2:, 1])
        # Assign a branch color only when both child subtrees share the same cut label.
        node_cluster = dict(enumerate(labels))
        for i, (left, right, _, _) in enumerate(linkage):
            a, b = node_cluster[int(left)], node_cluster[int(right)]
            node_cluster[n + i] = a if a == b else None
        branch_colors = {cluster: to_hex(color) for cluster, color in cluster_palette.items()}
        dendrogram(linkage, no_labels=True,
                   link_color_func=lambda node: branch_colors.get(node_cluster[node], "#41464f"), ax=tree)
        tree.set(ylabel="Ward height", xticks=[])
        tree.spines[["top", "right", "bottom"]].set_visible(False)
        for boundary in boundaries:
            tree.axvline(10 * (boundary + .5), color="#a7aab2", lw=.55, alpha=.5, zorder=0)
        strip = np.array([[list(type_palette).index(types[i]) for i in order],
                          [len(type_palette) + list(animal_palette).index(animals[i]) for i in order],
                          [len(type_palette) + len(animal_palette) + groups.index(labels[i]) for i in order]])
        colors = list(type_palette.values()) + list(animal_palette.values()) + [cluster_palette[c] for c in groups]
        band.imshow(strip, aspect="auto", interpolation="nearest", cmap=ListedColormap(colors),
                    vmin=-.5, vmax=len(colors)-.5)
        band.set(xticks=[])
        band.set_yticks([0, 1, 2], ["Neuron type", "Animal ID", "Candidate cluster"], fontsize=8)
        band.tick_params(axis="y", length=0)
        band.spines[:].set_visible(False)
        for boundary in boundaries:
            band.axvline(boundary, color="white", lw=.55, alpha=.9)
        length_values = length_values[order]
        strength_cmap = plt.get_cmap("viridis").with_extremes(bad="#edf0f3")
        for side, ax in enumerate(axes):
            values = length_values[:, side*w:(side+1)*w].T
            im = ax.imshow(np.ma.masked_equal(values, 0), aspect="auto", interpolation="nearest",
                           cmap=strength_cmap, vmin=0, vmax=scale_max)
            ax.set_title(["Ipsilateral targets", "Contralateral targets"][side], loc="left",
                         fontsize=10, fontweight="bold", pad=3)
            ax.set_yticks(range(w), regions, fontsize=8)
            ax.set_xticks([])
            ax.tick_params(axis="y", length=0)
            for boundary in boundaries:
                ax.axvline(boundary, color="#66717d", lw=.5, alpha=.65)
            for spine in ax.spines.values():
                spine.set_color("#a7aab2")
                spine.set_linewidth(.55)
        axes[-1].set_xlabel("Neurons in dendrogram order")
        cb = fig.colorbar(im, cax=cax)
        cb.set_label("Projection strength\nlog10(1 + retained length)", fontsize=9)
        draw_hierarchy_key(fig, (.14, key_bottom, .78, key_height), sections)
        atlas_display = atlas_insula_ids is not None
        title = "Atlas-selected macaque insula projection hierarchy" if atlas_display else "Insula projection matrix and morphology hierarchy"
        cohort = f"{n} of {parent_n} neurons  |  inherited candidate k={k}" if atlas_display else f"{n} neurons  |  candidate k={k}"
        fig.suptitle(title, y=.985, fontsize=17)
        fig.text(.53, .947, f"{cohort}  |  type penalty {factor:g} × max distance",
                 ha="center", fontsize=10)
        fig.text(.14,.026, f"{region_scope} ({retained_fraction:.1%} mean coverage). "
                 f"Pale gray indicates zero stored strength. Length: {length_unit}.\n"
                 "Layout adapted from Gou et al., Cell 2025, Fig. 2A.", fontsize=8)
    elif style == "distance_matrix":
        fig = plt.figure(figsize=(12, 18)); gs = fig.add_gridspec(3, 2, height_ratios=[2, .45, 8], width_ratios=[8,.2], left=.08, right=.93, bottom=.08, top=.80, hspace=.04, wspace=.08)
        tree=fig.add_subplot(gs[0,0]); band=fig.add_subplot(gs[1,0]); ax=fig.add_subplot(gs[2,0]); cax=fig.add_subplot(gs[2,1])
        dendrogram(fit["tree"], no_labels=True, color_threshold=0, above_threshold_color="#555555", ax=tree)
        tree.set_ylabel("Ward height"); tree.set_xticks([])
        names=list(type_palette); anames=list(animal_palette)
        strips=np.array([[names.index(types[i]) for i in order], [len(names)+anames.index(animals[i]) for i in order],
                         [len(names)+len(anames)+groups.index(labels[i]) for i in order]])
        colors=list(type_palette.values())+list(animal_palette.values())+[cluster_palette[c] for c in groups]
        band.imshow(strips, aspect="auto", interpolation="nearest", cmap=ListedColormap(colors), vmin=-.5, vmax=len(colors)-.5)
        band.set_yticks([0,1,2], ["Type", "Monkey", "Cluster"], fontsize=7);band.set_xticks([])
        values=fit["distance"][np.ix_(order,order)];im=ax.imshow(values, cmap="magma", interpolation="nearest", aspect="auto", vmin=0)
        for line in boundaries: ax.axhline(line,color="white",lw=.45,alpha=.7);ax.axvline(line,color="white",lw=.45,alpha=.7)
        ax.set(xlabel="Neurons in dendrogram order",ylabel="Neurons in dendrogram order")
        fig.colorbar(im,cax=cax,label="Clustering distance (includes type penalty)")
        fig.legend(handles=legend,loc="upper center",ncol=len(legend),bbox_to_anchor=(.5,.97),frameon=False,fontsize=8)
        fig.legend(handles=animal_legend,loc="upper center",ncol=len(animal_legend),bbox_to_anchor=(.5,.945),frameon=False,fontsize=7)
        fig.legend(handles=cluster_legend,loc="upper center",ncol=len(cluster_legend),bbox_to_anchor=(.5,.92),frameon=False,fontsize=7)
        fig.suptitle(f"Clustering distance | candidate k={k}",y=.995,fontsize=15)
        fig.text(.08,.025,"White lines show the candidate cluster cut. Type-guided distances include the declared penalty.",fontsize=9)
    else:
        means = np.array([projection[labels == c].mean(axis=0) for c in groups])
        prevalence = np.array([(projection[labels == c] > prevalence_threshold).mean(axis=0) for c in groups])
        fig, axes = plt.subplots(2,2,figsize=(17,9),layout="constrained",sharex=True,sharey=True)
        for side in range(2):
            m=means[:,side*w:(side+1)*w]; q=prevalence[:,side*w:(side+1)*w]
            im=axes[0,side].imshow(np.log10(1+100*m),cmap="viridis",vmin=0,vmax=np.log10(101),aspect="auto",interpolation="nearest")
            axes[0,side].set_title(["Ipsilateral mean fraction", "Contralateral mean fraction"][side])
            xx,yy=np.meshgrid(np.arange(w),np.arange(len(groups)))
            axes[1,side].scatter(xx.ravel(),yy.ravel(),s=(q.ravel()*180),c=np.log10(1+100*m.ravel()),cmap="viridis",vmin=0,vmax=np.log10(101),edgecolors="none")
            axes[1,side].set_title("Mean fraction and prevalence")
            axes[1,side].set_xticks(range(w),regions,rotation=55,ha="right",fontsize=8)
        axes[0,0].set_yticks(range(len(groups)),[f"C{c} (n={cluster_counts[str(c)]})" for c in groups]);axes[1,0].set_yticks(range(len(groups)),[f"C{c} (n={cluster_counts[str(c)]})" for c in groups])
        cb=fig.colorbar(im,ax=axes,shrink=.65,label="Mean bilateral projection fraction (log display)")
        cb.set_ticks(np.log10(1+100*np.array([0,.01,.05,.1,.5,1])),labels=["0","1%","5%","10%","50%","100%"])
        dots=[Line2D([],[],marker="o",linestyle="",color="#6b8e23",markersize=np.sqrt(180*x),label=f"{x:.0%}") for x in (.25,.5,1)]
        fig.legend(handles=dots,title=f"Fraction of neurons > {prevalence_threshold:.1%} (local descriptive threshold)",loc="outside lower center",ncol=3,frameon=False)
        fig.suptitle(f"Candidate k={k}: cluster projection summary\n{region_scope}; mean fraction retained {retained_fraction:.1%}; normalized over all bilateral L3 regions.\nMeans mask heterogeneity; dot size is not a p-value.")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream: fig.savefig(stream,format="png",dpi=dpi,bbox_inches="tight",pad_inches=.12)
    finally:
        plt.close(fig)
    result = {"style":style,"dpi":dpi,"prevalence_threshold":prevalence_threshold,"cluster_counts":cluster_counts,
            "order":[identities[i] for i in order],"regions":list(regions),"display_k":k,
            "length_unit":length_unit if style == "neuron_projection" else None,
            "total_regions":total_regions,"mean_fraction_retained":retained_fraction}
    if style == "neuron_projection":
        result.update(hierarchy_key="framed", parent_neurons=parent_n, strength_scale=[0., scale_max],
                      cohort_display="atlas_insula_restriction" if atlas_insula_ids is not None else "full")
    return result


def render_projection_distribution(labels, identities, projection, regions, profile, output,
                                   top_regions=6, seed=42, dpi=None, total_regions=None):
    """Display per-neuron fraction spread using existing cluster assignments."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    n, w = len(identities), len(regions)
    labels = np.asarray(labels); projection = np.asarray(projection, dtype=float)
    dpi = profile["plots"].get("dpi", 190) if dpi is None else dpi
    if (not n or len(set(identities)) != n or len(labels) != n or projection.shape != (n,2*w)
            or not np.isfinite(projection).all() or np.any(projection < 0)
            or np.any(projection.sum(axis=1) > 1 + 1e-9)):
        raise ValueError("Need unique identities, aligned labels and valid bilateral fractions")
    if type(top_regions) is not int or not 1 <= top_regions <= w or type(seed) is not int or seed < 0:
        raise ValueError("Invalid displayed region count or jitter seed")
    if type(dpi) is not int or not 72 <= dpi <= 600:
        raise ValueError("DPI must be 72..600")
    groups = sorted(set(labels)); rng = np.random.default_rng(seed)
    counts = {str(c): int(np.sum(labels == c)) for c in groups}
    fig, axes = plt.subplots(top_regions, 2, figsize=(15, 2.45*top_regions+2), squeeze=False, sharex=True, sharey=True)
    for row in range(top_regions):
        for side in range(2):
            ax = axes[row,side]
            values = [projection[labels == c, row+side*w] for c in groups]
            transformed = [np.log10(1+100*v) for v in values]
            ax.boxplot(transformed, positions=np.arange(1,len(groups)+1), widths=.34,
                       showfliers=False, patch_artist=True,
                       boxprops={"facecolor":"#eeeeee", "edgecolor":"#444444", "linewidth":.8},
                       medianprops={"color":"#111111", "linewidth":1.2},
                       whiskerprops={"color":"#555555", "linewidth":.7}, capprops={"color":"#555555", "linewidth":.7})
            for j, values_j in enumerate(transformed):
                offsets = rng.uniform(-.22,.22,len(values_j))
                ax.scatter(j+1+offsets, values_j, s=5, alpha=.20, color="#2878b5", edgecolors="none", rasterized=True)
            ax.set_title(f"{regions[row]} — {'ipsilateral' if side == 0 else 'contralateral'}", fontsize=10)
            ax.set_ylim(-.04,np.log10(101)+.03); ax.grid(axis="y", color="#dddddd", linewidth=.5)
            if side == 0: ax.set_ylabel("Fraction of bilateral total", fontsize=8)
            ax.set_yticks(np.log10(1+100*np.array([0,.01,.05,.1,.5,1])),["0","1%","5%","10%","50%","100%"],fontsize=7)
    for ax in axes[-1]: ax.set_xticks(np.arange(1,len(groups)+1), [f"C{c}\n(n={counts[str(c)]})" for c in groups], fontsize=8)
    fig.legend(handles=[Line2D([],[],marker="o",linestyle="",color="#2878b5",alpha=.5,label="Individual neuron"),
                        Line2D([],[],color="#111111",label="Median; box: 25th–75th percentile")],
               loc="upper center", bbox_to_anchor=(.5,.955), ncol=2, frameon=False, fontsize=9)
    fig.suptitle(f"Projection distributions | type-guided candidate k={profile['clustering']['display_k']}\n"
                 "Legacy retained atlas-voxel length proxy; per-neuron bilateral fractions (log display)", y=.995, fontsize=13)
    fig.text(.05,.015, "All neurons shown, including zeros. Fractions normalize over ALL bilateral L3 regions; "
             "top displayed regions are selected by cohort mean. Jitter separates points only.\n"
             "Box whiskers follow 1.5 × IQR; points show all values. No statistical significance or biological subtype is implied.", fontsize=8)
    fig.subplots_adjust(left=.08,right=.98,bottom=.08,top=.92,hspace=.55,wspace=.18)
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        with output.open("xb") as stream: fig.savefig(stream,format="png",dpi=dpi,bbox_inches="tight",pad_inches=.12)
    finally:
        plt.close(fig)
    return {"kind":"per_neuron_fraction_distribution","regions":list(regions[:top_regions]),"total_regions":total_regions,
            "normalization":"per-neuron over all bilateral L3 regions", "display_transform":"log10(1+100*fraction)",
            "jitter_seed":seed,"dpi":dpi,"cluster_counts":counts,"points_include_zero":True,
            "definition":"legacy retained atlas-voxel length proxy; type-guided candidate, not an axon-arbor measurement"}


def render_morphologies(fit, identities, profile, producer_plan, output):
    """Legacy medoid/farthest selection, two coordinate planes, full shared extent."""
    import tempfile
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from .fnt_pipeline import preprocess_swc
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    settings = profile["plots"]
    planes = settings.get("morphology_planes", [[0, 1], [0, 2]])
    if any(len(p) != 2 or len(set(p)) != 2 or any(v not in (0,1,2) for v in p) for p in planes):
        raise ValueError("Morphology planes require two distinct coordinate axes")
    labels = fit["cuts"][profile["clustering"]["display_k"]]
    distance = fit["distance"]
    cases = {c["sample_id"]+"_"+c["neuron_id"].removesuffix(".swc"): c for c in producer_plan["cases"]}
    examples, clusters = [], sorted(set(labels))
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        for cluster in clusters:
            members = np.flatnonzero(labels == cluster)
            med = members[np.argmin(distance[np.ix_(members,members)].sum(axis=1))]
            far = members[np.argmax(distance[med,members])]
            pair = []
            for role, index in [("medoid",med),("farthest",far)]:
                identity = identities[index]
                case = cases[identity]
                source = Path(case["swc_path"])
                if file_sha256(source) != case["swc_sha256"]:
                    raise ValueError("Morphology source hash mismatch")
                processed = Path(temporary)/(identity+".swc")
                transform = preprocess_swc(source,processed,producer_plan["preprocessing"]["mode"],producer_plan["preprocessing"]["midline_x"])
                nodes = np.loadtxt(processed,ndmin=2)
                lookup = {int(row[0]):i for i,row in enumerate(nodes)}
                if len(lookup) != len(nodes):
                    raise ValueError("Duplicate SWC node IDs")
                roots = nodes[nodes[:,6] == -1]
                if len(roots) != 1:
                    raise ValueError("Morphology requires one declared SWC root")
                edges = np.array([(lookup[int(row[6])],i) for i,row in enumerate(nodes) if row[6] != -1],dtype=int).reshape(-1,2)
                xyz = nodes[:,2:5] - roots[0,2:5]
                pair.append({"role":role,"identity":identity,"source":str(source),"source_sha256":case["swc_sha256"],"transform":transform,"xyz":xyz,"edges":edges})
            examples.append({"cluster":int(cluster),"n":len(members),"pair":pair})
    coordinates = np.concatenate([p["xyz"] for e in examples for p in e["pair"]])
    lo, hi = coordinates.min(axis=0), coordinates.max(axis=0)
    pad = np.maximum((hi-lo)*.04,1)
    # One common physical span keeps equal scale without squeezing narrow axes.
    center = (lo+hi)/2
    span = float(np.max(hi-lo+2*pad))
    lo, hi = center-span/2, center+span/2
    fig,axes = plt.subplots(len(clusters),2*len(planes),figsize=(3.6*2*len(planes),3.8*len(clusters)),squeeze=False,layout="constrained")
    colors = {"medoid":"#2878b5","farthest":"#d55e00"}
    for row,example in enumerate(examples):
        for col,plane in enumerate(planes):
            for member,item in enumerate(example["pair"]):
                ax = axes[row,col*2+member]
                xy = item["xyz"][:,plane]
                ax.add_collection(LineCollection(xy[item["edges"]],colors=colors[item["role"]],linewidths=.65,alpha=.85))
                ax.scatter([0],[0],s=14,c="black",marker="+")
                ax.set(xlim=(lo[plane[0]],hi[plane[0]]),ylim=(lo[plane[1]],hi[plane[1]]),xlabel="XYZ"[plane[0]]+" from root (source units)",ylabel="XYZ"[plane[1]]+" from root (source units)",title=f"C{example['cluster']} (n={example['n']}) | {item['role']}\n{item['identity']}")
                ax.title.set_fontsize(9)
                from matplotlib.ticker import MaxNLocator
                ax.xaxis.set_major_locator(MaxNLocator(4))
                ax.yaxis.set_major_locator(MaxNLocator(4))
                ax.tick_params(labelsize=7)
                ax.set_aspect("equal")
    fig.suptitle("Candidate morphology | blue: medoid; orange: farthest; +: SWC root\nRoot-centered display; identical physical scale; full extent; XY and XZ coordinate views")
    with output.open("xb") as stream:fig.savefig(stream,format="png",dpi=settings.get("dpi",190),bbox_inches="tight")
    plt.close(fig)
    return {"selection":"minimum sum within-cluster fitted distance; farthest from medoid; first tie in matrix order","planes":planes,"display":"root-centered only, shared full shown-neuron extent","examples":[{"cluster":e["cluster"],"n":e["n"],"pair":[{k:v for k,v in p.items() if k not in ("xyz","edges")} for p in e["pair"]]} for e in examples]}


def render_parameter_review(metrics, profile, output):
    """Show complementary diagnostics without choosing a winning cut."""
    import matplotlib.pyplot as plt
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    columns = [("subsample_ari_mean","Fixed-matrix resampling ARI"),
               ("projection_sqrt_euclidean_silhouette","Projection silhouette: sqrt fractions / Euclidean"),
               ("largest_cluster_fraction","Fraction in largest cluster"),
               ("sample_cluster_ari","Agreement between clusters and monkey IDs (ARI)")]
    fig,axes = plt.subplots(2,2,figsize=(13,9),layout="constrained")
    colors = {factor: plt.get_cmap("tab10")(i) for i,factor in enumerate(sorted(metrics.penalty_factor.unique()))}
    for ax,(column,title) in zip(axes.ravel(),columns):
        for (variant,factor),group in metrics.groupby(["variant","penalty_factor"],sort=False):
            group = group.sort_values("requested_k")
            ax.plot(group.requested_k,group[column],marker="o",markersize=3,color=colors[factor],
                    linestyle="-" if variant == "primary" else "--",label=f"{variant}: penalty {factor:g}")
        ax.axvline(profile["clustering"]["display_k"],color=".65",ls=":")
        ax.set(title=title,xlabel="Candidate cluster count",xticks=sorted(metrics.requested_k.unique()))
        ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8)
    fig.suptitle("Candidate parameter comparison — no automatic winner\nType-guided stability and related projection evidence do not establish biological types")
    with output.open("xb") as stream:fig.savefig(stream,format="png",dpi=profile["plots"].get("dpi",190),bbox_inches="tight")
    plt.close(fig)


def render_monkey_composition(labels, animals, profile, output):
    """Counts and within-monkey fractions expose unequal animal sampling."""
    import matplotlib.pyplot as plt
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    counts = pd.crosstab(pd.Series(animals,name="Monkey"),pd.Series(labels,name="Cluster"))
    fractions = counts.div(counts.sum(axis=1),axis=0)
    fig,axes = plt.subplots(1,2,figsize=(13,5),layout="constrained")
    for ax,frame,title,is_fraction in [(axes[0],counts,"Neuron counts",False),(axes[1],fractions,"Fraction of each monkey across clusters",True)]:
        image = ax.imshow(frame.to_numpy(),aspect="auto",cmap="Blues",vmin=0,vmax=1 if is_fraction else max(1,counts.to_numpy().max()))
        ax.set(xticks=range(len(frame.columns)),xticklabels=[f"C{c}" for c in frame.columns],yticks=range(len(frame)),yticklabels=[f"{a} (n={counts.loc[a].sum()})" for a in frame.index],title=title,xlabel="Candidate cluster",ylabel="Monkey")
        for i in range(len(frame)):
            for j in range(len(frame.columns)):
                value = frame.iloc[i,j]
                ax.text(j,i,f"{value:.0%}" if is_fraction else str(value),ha="center",va="center",fontsize=8,color="white" if value > image.get_clim()[1]*.5 else "black")
        fig.colorbar(image,ax=ax,shrink=.8)
    fig.suptitle("Monkey composition at the display cut — unequal sampling remains explicit")
    with output.open("xb") as stream:fig.savefig(stream,format="png",dpi=profile["plots"].get("dpi",190),bbox_inches="tight")
    plt.close(fig)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    for name in ["profile", "distance", "joined-fnt", "tables", "output"]:
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--title", default="Legacy-compatible FNT clustering and projection review")
    parser.add_argument("--dpi", type=int)
    parser.add_argument("--top-regions", type=int)
    parser.add_argument("--display-k", type=int)
    parser.add_argument("--missing-region-policy", choices=["error", "sparse_zero"], default="error")
    parser.add_argument("--morphologies", action="store_true")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--compare-unknown-types", action="store_true")
    parser.add_argument("--source-workbook", type=Path)
    parser.add_argument("--producer-receipt", type=Path)
    parser.add_argument("--alternative-style", action="append", choices=["neuron_projection", "distance_matrix", "cluster_summary"], default=[], help="Render selected optional style; repeat to choose several")
    parser.add_argument("--atlas-insula-receipt", type=Path,
                        help="Restrict neuron_projection to the verified atlas insula roster, keeping the parent hierarchy")
    parser.add_argument("--prevalence-threshold", type=float, default=.01, help="Local descriptive fraction threshold for cluster summary dot size")
    parser.add_argument("--length-unit", default="retained atlas-voxel length (source-table units)", help="Declared source projection length units for neuron-level display")
    parser.add_argument("--projection-distribution", action="store_true", help="Render per-neuron cluster fraction distributions")
    parser.add_argument("--distribution-regions", type=int, default=6, help="Number of top-ranked regions shown in distribution plot")
    parser.add_argument("--distribution-seed", type=int, default=42, help="Seed for horizontal display jitter only")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.atlas_insula_receipt and "neuron_projection" not in args.alternative_style:
        parser.error("--atlas-insula-receipt requires --alternative-style neuron_projection")
    if args.output.exists():
        raise FileExistsError(args.output)
    profile = load_profile(args.profile)
    settings = profile["plots"]
    if args.dpi is not None: settings["dpi"] = args.dpi
    if args.top_regions is not None: settings["top_regions"] = args.top_regions
    if args.display_k is not None:
        if args.display_k not in profile["clustering"]["candidate_k"]: raise ValueError("Display cut must be in candidate_k")
        profile["clustering"]["display_k"] = settings["boundaries_k"] = args.display_k
    if not 72 <= settings.get("dpi", 190) <= 600: raise ValueError("DPI must be 72..600")
    if not 0 <= args.prevalence_threshold <= 1: raise ValueError("Prevalence threshold must be between zero and one")
    if len(args.alternative_style) != len(set(args.alternative_style)): raise ValueError("Alternative styles must be unique")
    if settings["projection_sides"] != ["ipsi", "contra"] or settings["display_transform"] != "log10(1+100*fraction)":
        raise ValueError("Unsupported projection display semantics")
    if args.producer_receipt:
        producer = json.loads(args.producer_receipt.read_text())
        for key, path in [("distance", args.distance), ("joined", args.joined_fnt)]:
            if file_sha256(path) != producer[key+"_sha256"]:
                raise ValueError("Producer receipt does not match analysis input")
    if args.morphologies and not args.producer_receipt:
        raise ValueError("Morphology requires a producer receipt")
    if args.source_workbook and not args.source_workbook.is_file():
        raise FileNotFoundError(args.source_workbook)
    matrix, metadata = read_fnt_distances(args.distance, args.joined_fnt)
    ids = list(matrix.index)
    summary, sides, sources = load_tables(json.loads(args.tables.read_text()), ids, settings["projection_level"], args.missing_region_policy)
    shown, regions, fraction = prepare_projection(sides["ipsi"], sides["contra"], ids, settings["top_regions"])
    atlas_ids = atlas_insula_display_ids(args.atlas_insula_receipt, summary) if args.atlas_insula_receipt else None
    fits = fit_profile(matrix.to_numpy(), summary.Neuron_Type.tolist(), profile)
    receipt = {"renderer_version": VERSION, "status": "dry_run", "profile": profile,
               "profile_sha256": file_sha256(args.profile), "tables": sources, "distance": metadata,
               "identities": ids, "regions": regions, "projection_fraction_shape": list(fraction.shape),
               "title": args.title, "output": str(args.output)}
    receipt["requested"] = {"diagnostics": args.diagnostics, "compare_unknown_types": args.compare_unknown_types,
                            "source_workbook": str(args.source_workbook) if args.source_workbook else None,
                            "producer_receipt": str(args.producer_receipt) if args.producer_receipt else None,
                            "alternative_styles": args.alternative_style, "prevalence_threshold": args.prevalence_threshold,
                            "length_unit": args.length_unit, "projection_distribution": args.projection_distribution,
                            "distribution_regions": args.distribution_regions, "distribution_seed": args.distribution_seed}
    if args.atlas_insula_receipt:
        receipt["atlas_insula_display"] = {
            "receipt": str(args.atlas_insula_receipt.resolve()), "sha256": file_sha256(args.atlas_insula_receipt),
            "neurons": len(atlas_ids), "parent_neurons": len(ids), "hierarchy_key": "framed",
            "hierarchy": "restrict parent tree", "projection_rank_and_scale": "parent cohort",
        }
    if args.dry_run:
        print(json.dumps(receipt, indent=2))
        return
    args.output.mkdir(parents=True, exist_ok=False)
    receipt["orders"] = render_review(fits, summary.Neuron_Type.tolist(), ids, shown, regions,
                                       profile, args.output/"cluster_projection_review.png", args.title, animals=summary.AnimalID.astype(str).tolist() if summary.AnimalID.nunique() > 1 else None)
    if args.alternative_style:
        lengths = np.concatenate([sides[s].loc[ids].reindex(columns=regions, fill_value=0).to_numpy(float) for s in ("ipsi", "contra")],axis=1)
        receipt["alternative_styles"] = []
        for style in args.alternative_style:
            selection = atlas_ids if style == "neuron_projection" else None
            suffix = "_atlas_insula" if selection is not None else ""
            result = render_alternative(
                fits[profile["clustering"]["penalty_factor"]], summary.Neuron_Type.tolist(),
                summary.AnimalID.astype(str).tolist(), ids, shown, regions, profile,
                args.output / (style + suffix + ".png"), style, args.prevalence_threshold,
                projection_lengths=lengths, length_unit=args.length_unit,
                total_regions=fraction.shape[1] // 2, atlas_insula_ids=selection,
            )
            receipt["alternative_styles"].append(result)
    if args.projection_distribution:
        receipt["projection_distribution"] = render_projection_distribution(
            fits[profile["clustering"]["penalty_factor"]]["cuts"][profile["clustering"]["display_k"]], ids, shown, regions,
            profile, args.output/"projection_distribution.png", args.distribution_regions, args.distribution_seed,
            total_regions=fraction.shape[1]//2)
    for factor, fit in fits.items():
        pd.DataFrame({"FNT_NeuronID": ids, **{f"k_{k}": v for k,v in fit["cuts"].items()}}).to_csv(
            args.output/f"assignments_penalty{factor:g}.csv", index=False)
    assignments = [(f"primary_penalty{f:g}", args.output/f"assignments_penalty{f:g}.csv") for f in fits]
    variants = [("primary", profile, fits)]
    if args.compare_unknown_types:
        import copy
        alternate = copy.deepcopy(profile)
        current = profile["clustering"].get("unknown_type_policy", "legacy_label")
        alternate["clustering"]["unknown_type_policy"] = "legacy_label" if current == "known_only" else "known_only"
        other = fit_profile(matrix.to_numpy(), summary.Neuron_Type.tolist(), alternate)
        # Zero penalty is identical; retain only one copy of its assignments/diagnostics.
        other = {f: v for f, v in other.items() if f != 0}
        variants.append((alternate["clustering"]["unknown_type_policy"], alternate, other))
        for factor, fit in other.items():
            name = f"{variants[-1][0]}_penalty{factor:g}"
            path = args.output/f"assignments_{name}.csv"
            pd.DataFrame({"FNT_NeuronID": ids, **{f"k_{k}": v for k,v in fit["cuts"].items()}}).to_csv(path,index=False)
            assignments.append((name,path))
    if args.diagnostics:
        from .review_profile import evaluate_profile
        tables = [[], [], []]
        for label, variant, fitted in variants:
            results = evaluate_profile(fitted, variant, summary.AnimalID.astype(str).tolist(), fraction)
            for destination, frame in zip(tables, results):
                destination.append(frame.assign(variant=label, unknown_type_policy=variant["clustering"].get("unknown_type_policy","legacy_label")))
        for name, frames in zip(["parameter_diagnostics", "cluster_stability", "monkey_holdouts"], tables):
            pd.concat(frames,ignore_index=True).to_csv(args.output/(name+".csv"),index=False)
        render_parameter_review(pd.concat(tables[0],ignore_index=True),profile,args.output/"parameter_review.png")
    if summary.AnimalID.nunique() > 1:
        counts = render_monkey_composition(fits[profile["clustering"]["penalty_factor"]]["cuts"][profile["clustering"]["display_k"]],summary.AnimalID.astype(str).tolist(),profile,args.output/"monkey_composition.png")
        counts.to_csv(args.output/"monkey_cluster_counts.csv")
    if args.source_workbook:
        from .clustered_table import evolve
        receipt["evolved_table"] = evolve(args.source_workbook,args.output/"neuron_table_clustered.xlsx",None,assignments)
    if args.morphologies:
        receipt["morphologies"] = render_morphologies(fits[profile["clustering"]["penalty_factor"]],ids,profile,producer["plan"],args.output/"representative_morphologies.png")
    receipt["status"] = "rendered_candidate"
    receipt["outputs_sha256"] = {p.name: file_sha256(p) for p in args.output.iterdir() if p.is_file()}
    (args.output/"receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "neurons": len(ids), "output": str(args.output)}))


if __name__ == "__main__":
    main()
