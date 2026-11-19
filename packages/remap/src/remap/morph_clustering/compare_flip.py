"""Matched, source-preserving comparison of two completed FNT flip variants.

Version: 0.1.2 (local/unreleased)
Last updated: 2026-11-18
Change history: ../../../CHANGELOG.md
- 2026-11-18: Normalize provenance-only source_config omitted by full producer receipts;
  all resolved scientific fields remain strictly compared.
- 2026-11-18: Initial matched comparison.
- 2026-11-18: Add receipt-checked plot-only effect summary; separate guided rows and label actual neuron counts.
Status: candidate
"""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import adjusted_rand_score
from .fnt_pipeline import read_fnt_distances
from .review_profile import load_profile, fit_profile

VERSION = "0.1.2"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_pairs(path):
    frame = pd.read_csv(path, sep="\t")
    ij = frame[["I", "J"]].to_numpy(float)
    if not np.isfinite(ij).all() or not np.equal(ij, np.floor(ij)).all():
        raise ValueError("Noninteger pair indices")
    frame[["I", "J"]] = np.sort(ij.astype(int), axis=1)
    if frame.duplicated(["I", "J"]).any():
        raise ValueError("Duplicate unordered pair")
    return frame.set_index(["I", "J"]).sort_index()


def compare(folded, reflected, summary, profile_path, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    receipts = [json.loads(Path(p).read_text(encoding="utf-8")) for p in (folded, reflected)]
    plans = [r["plan"] for r in receipts]
    # Only execution bookkeeping and flip mode may differ. Fail closed otherwise.
    def scientific_plan(plan):
        result = dict(plan)
        # validate_settings retains the original configuration as source_config,
        # but _produce_fnt deliberately omits it from serialized receipts. The
        # resolved cases/tools/preprocessing/decimation/clustering remain below.
        for key in ("output_root", "cache_root", "timeout_seconds", "source_config"):
            result.pop(key, None)
        result["preprocessing"] = dict(result["preprocessing"])
        result["preprocessing"].pop("mode")
        return result
    if scientific_plan(plans[0]) != scientific_plan(plans[1]):
        raise ValueError("Unmatched scientific plans: more than flip mode differs")
    if [p["preprocessing"]["mode"] for p in plans] != ["legacy_nodewise_fold", "whole_neuron_reflect"]:
        raise ValueError("Require folded then whole-neuron-reflected receipts")
    matrices, pairs = [], []
    for r in receipts:
        if "status" in r and r["status"] != "complete":
            raise ValueError("Producer receipt explicitly incomplete")
        joined = r.get("joined_fnt")
        if sha(r["distance"]) != r["distance_sha256"] or sha(joined) != r["joined_sha256"]:
            raise ValueError("Receipt input hash mismatch")
        matrix, _ = read_fnt_distances(Path(r["distance"]), Path(joined))
        matrices.append(matrix)
        pairs.append(canonical_pairs(r["distance"]))
    identities = list(matrices[0].index)
    expected = [c["sample_id"]+"_"+c["neuron_id"].removesuffix(".swc") for c in plans[0]["cases"]]
    if identities != expected:
        raise ValueError("Joined marker order differs from source plan")
    if identities != list(matrices[1].index) or not pairs[0].index.equals(pairs[1].index):
        raise ValueError("Pair/identity ordering mismatch")
    for tool in plans[0]["tools"].values():
        if sha(tool["path"]) != tool["sha256"]:
            raise ValueError("Executable changed since producer receipt")
    crossing = []
    mid = plans[0]["preprocessing"]["midline_x"]
    for case in plans[0]["cases"]:
        path = Path(case["swc_path"])
        if sha(path) != case["swc_sha256"]:
            raise ValueError("Source hash mismatch")
        nodes = np.loadtxt(path, ndmin=2)
        roots = nodes[nodes[:, 6] == -1]
        if len(roots) != 1 or roots[0, 1] != 1:
            raise ValueError("Whole-neuron comparison requires one type-1 soma root")
        crossing.append(bool((nodes[:, 2] < mid).any() and (nodes[:, 2] > mid).any()))
    masks = {"all": np.ones(len(pairs[0]), dtype=bool)}
    masks["involves_crossing"] = np.array([crossing[i] or crossing[j] for i, j in pairs[0].index])
    masks["neither_crossing"] = ~masks["involves_crossing"]
    metrics = []
    for group, mask in masks.items():
        for field in ("Score", "Match", "NoMatch"):
            a, b = (p[field].to_numpy(float)[mask] for p in pairs)
            absolute = np.abs(b-a)
            nonzero = a != 0
            metrics.append({"pair_group": group, "field": field, "pairs": len(a),
                            "exact": int(np.count_nonzero(a == b)),
                            "median_absolute_change": float(np.median(absolute)) if len(a) else None,
                            "p95_absolute_change": float(np.percentile(absolute, 95)) if len(a) else None,
                            "max_absolute_change": float(absolute.max()) if len(a) else None,
                            "max_relative_change_nonzero_baseline": float((absolute[nonzero]/np.abs(a[nonzero])).max()) if nonzero.any() else None,
                            "zero_baseline_pairs": int((~nonzero).sum()),
                            "zero_baseline_changed": int(((~nonzero) & (absolute != 0)).sum())})
    profile = load_profile(profile_path)
    table = pd.read_csv(summary, dtype={"FNT_NeuronID": str}).set_index("FNT_NeuronID")
    if not table.index.is_unique:
        raise ValueError("Duplicate Summary identities")
    types = table.loc[identities, "Neuron_Type"].tolist()
    fits = [fit_profile(m.to_numpy(), types, profile) for m in matrices]
    clustering = []
    for penalty in fits[0]:
        for k, a in fits[0][penalty]["cuts"].items():
            b = fits[1][penalty]["cuts"][k]
            contingency = pd.crosstab(a, b).to_numpy()
            row, col = linear_sum_assignment(-contingency)
            matched = int(contingency[row, col].sum())
            clustering.append({"penalty_factor": penalty, "requested_k": k,
                               "ari": adjusted_rand_score(a, b),
                               "aligned_reassigned": len(a)-matched,
                               "aligned_reassigned_fraction": 1-matched/len(a)})
    for case in plans[0]["cases"]:
        if sha(case["swc_path"]) != case["swc_sha256"]:
            raise ValueError("Source changed during comparison")
    output.mkdir(parents=True)
    pd.DataFrame(metrics).to_csv(output/"pair_changes.csv", index=False)
    results = pd.DataFrame(clustering)
    results.to_csv(output/"cluster_agreement.csv", index=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(11, 9), layout="constrained")
    axes = axes.ravel()
    for penalty, group in results.groupby("penalty_factor"):
        axes[0].plot(group.requested_k, group.ari, "o-", label=f"penalty {penalty:g}")
        axes[1].plot(group.requested_k, group.aligned_reassigned_fraction, "o-")
    axes[0].set(title="Fold versus whole-neuron reflection", ylabel="Partition agreement (ARI)", xlabel="Candidate k", ylim=(min(-.05, float(results.ari.min())-.05), 1.05))
    axes[1].set(title="After optimal label matching", ylabel="Fraction reassigned", xlabel="Candidate k", ylim=(-.05, 1.05))
    for axis in axes[:2]:
        axis.set_xticks(sorted(results.requested_k.unique()))
    axes[0].legend()
    score_a, score_b = [p["Score"].to_numpy(float) for p in pairs]
    scatter_cap = 50000
    shown = np.unique(np.linspace(0, len(score_a)-1, min(scatter_cap, len(score_a)), dtype=int))
    for group, color in [("neither_crossing", "#2878b5"), ("involves_crossing", "#d55e00")]:
        chosen = shown[masks[group][shown]]
        axes[2].scatter(np.log1p(score_a[chosen]), np.log1p(score_b[chosen]),
                        s=8, alpha=.45, color=color, label=group.replace("_", " "))
    maximum = float(np.log1p(max(score_a.max(), score_b.max())))
    axes[2].plot([0, maximum], [0, maximum], color=".4", ls="--", lw=1)
    axes[2].set(title=f"FNT Score comparison ({len(shown):,}/{len(score_a):,} pairs shown)",
                xlabel="log1p(folded Score)", ylabel="log1p(reflected Score)")
    axes[2].legend(fontsize=8)
    score_metrics = pd.DataFrame(metrics).query("field == 'Score'").set_index("pair_group")
    groups = ["neither_crossing", "involves_crossing"]
    for offset, (column, label) in enumerate([("median_absolute_change", "median"),
                                            ("p95_absolute_change", "95th percentile"),
                                            ("max_absolute_change", "maximum")]):
        axes[3].bar(np.arange(2)+(offset-1)*.25, np.log1p(score_metrics.loc[groups, column].to_numpy(float)),
                    width=.25, label=label)
    axes[3].set(title="Absolute Score change (all pairs)", ylabel="log1p(abs(reflected - folded))",
                xticks=[0, 1], xticklabels=["Neither crossing", "Involves crossing"])
    axes[3].legend(fontsize=8)
    fig.savefig(output/"flip_clustering_comparison.png", dpi=160)
    plt.close(fig)
    result = {"version": VERSION, "status": "matched comparison completed; not scientific acceptance",
              "input_receipts": [{"path": str(p), "sha256": sha(p)} for p in (folded, reflected)],
              "profile": str(profile_path), "profile_sha256": sha(profile_path),
              "summary": str(summary), "summary_sha256": sha(summary), "neurons": len(identities),
              "plan_comparison": "Strict equality of resolved scientific fields; source_config is provenance-only and omitted by full producer serialization",
              "crossing_neurons": [uid for uid, cross in zip(identities, crossing) if cross],
              "relative_change_definition": "abs(reflected-folded)/abs(folded); zero denominators counted separately, not assigned zero",
              "clustering_definition": "same frozen profile/types; optimal one-to-one cluster-label matching before reassignment counts",
              "score_scatter": {"pair_count": len(score_a), "shown": len(shown), "cap": scatter_cap,
                                "selection": "deterministic evenly spaced indices in canonical sorted pair order; summaries use all pairs"},
              "outputs_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()}}
    (output/"receipt.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result



def render_effect_summary(comparison_dir, output, dpi=180, overwrite=False):
    """Plot existing verified comparison; never refit clusters or rerun FNT."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    root, output = Path(comparison_dir), Path(output)
    if output.exists() and not overwrite:
        raise FileExistsError(output)
    if not isinstance(dpi, int) or not 72 <= dpi <= 600:
        raise ValueError("dpi must be 72..600")
    receipt = json.loads((root/"receipt.json").read_text(encoding="utf-8"))
    for name, digest in receipt["outputs_sha256"].items():
        if sha(root/name) != digest:
            raise ValueError("Comparison artifact changed: " + name)
    agreement = pd.read_csv(root/"cluster_agreement.csv")
    metrics = pd.read_csv(root/"pair_changes.csv")
    producers = []
    for ref in receipt["input_receipts"]:
        if sha(ref["path"]) != ref["sha256"]:
            raise ValueError("Producer receipt changed")
        producer = json.loads(Path(ref["path"]).read_text(encoding="utf-8"))
        if sha(producer["distance"]) != producer["distance_sha256"]:
            raise ValueError("Distance changed")
        producers.append(producer)
    pairs = [canonical_pairs(p["distance"]) for p in producers]
    if not pairs[0].index.equals(pairs[1].index):
        raise ValueError("Pair mismatch")
    identities = [c["sample_id"]+"_"+c["neuron_id"].removesuffix(".swc") for c in producers[0]["plan"]["cases"]]
    crossing = set(receipt["crossing_neurons"])
    mask = np.array([identities[i] in crossing or identities[j] in crossing for i,j in pairs[0].index])
    a,b = [p.Score.to_numpy(float) for p in pairs]
    eligible = mask & (a != 0)
    relative = np.sort(100*np.abs(b[eligible]-a[eligible])/np.abs(a[eligible]))
    factors = sorted(agreement.penalty_factor.unique())
    colors = ["#2864A5", "#D87821", "#25816C"]
    labels = ["Unguided" if f == 0 else f"Type-guided ({f:g})" for f in factors]
    fig, axes = plt.subplots(2,2,figsize=(13,9.5))
    fig.subplots_adjust(left=.09,right=.98,bottom=.14,top=.84,wspace=.32,hspace=.62)
    fig.suptitle("Different FNT distances can produce the same guided clusters",fontsize=18,x=.06,ha="left",y=.98)
    fig.text(.06,.92,f"{receipt['neurons']} neurons | {len(crossing)} cross the midline | matched sources and settings; only flip mode changes",fontsize=11,color="#475569")
    ax=axes[0,0]
    groups=["neither_crossing","involves_crossing"]
    for j,field in enumerate(["Score","Match","NoMatch"]):
        rows=metrics[metrics.field==field].set_index("pair_group").loc[groups]
        changed=rows.pairs-rows.exact
        x=np.arange(2)+(j-1)*.24
        bars=ax.bar(x,100*changed/rows.pairs,width=.22,color=colors[j],label=field)
        for bar,value in zip(bars,changed):
            ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+2,f"{int(value):,}",ha="center",fontsize=8)
    ax.set(title="A  Which pair values changed?",ylabel="Changed pairs (%)",ylim=(0,117),xticks=[0,1],xticklabels=[f"Neither neuron crosses\n{int((~mask).sum()):,} pairs", f"At least one crosses\n{int(mask.sum()):,} pairs"])
    ax.yaxis.set_major_formatter(PercentFormatter());ax.legend(frameon=False,ncol=3,fontsize=8,loc="upper left")
    ax=axes[0,1]
    pivot=agreement.pivot(index="penalty_factor",columns="requested_k",values="ari").loc[factors]
    im=ax.imshow(pivot.to_numpy(),cmap="YlGnBu",vmin=min(0,float(pivot.min().min())),vmax=1,aspect="auto")
    for i in range(len(factors)):
        for j,v in enumerate(pivot.iloc[i]):
            ax.text(j,i,f"{v:.2f}",ha="center",va="center",fontsize=7,color="white" if v>.65 else "black")
    ax.set(title="B  Cluster agreement across cuts",xlabel="Number of clusters (k)",xticks=range(len(pivot.columns)),xticklabels=pivot.columns,yticks=range(len(factors)),yticklabels=labels)
    fig.colorbar(im,ax=ax,pad=.02,fraction=.04,label="ARI (1 = identical)")
    ax=axes[1,0]
    cuts=[k for k in [7,9] if k in pivot.columns] or list(pivot.columns[-2:])
    maximum=1
    for i,(factor,label) in enumerate(zip(factors,labels)):
        vals=agreement[agreement.penalty_factor==factor].set_index("requested_k").loc[cuts,"aligned_reassigned"].to_numpy()
        maximum=max(maximum,int(vals.max()))
        bars=ax.bar(np.arange(len(cuts))+(i-(len(factors)-1)/2)*.24,vals,width=.22,color=colors[i%3],label=label)
        for bar,value in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,value+1,str(value),ha="center",fontsize=10)
    ax.set(title="C  How many neurons change cluster?",ylabel=f"Reassigned neurons / {receipt['neurons']}",xticks=range(len(cuts)),xticklabels=[f"k = {k}" for k in cuts],ylim=(0,maximum*1.35+4))
    ax.legend(frameon=False,fontsize=8,loc="upper right")
    ax=axes[1,1]
    ax.plot(relative,np.arange(1,len(relative)+1)/len(relative)*100,color=colors[1],lw=2)
    ax.set_xscale("symlog",linthresh=1)
    ax.set(title="D  Size of Score changes for crossing pairs",xlabel="Absolute relative change (%) — nonlinear axis",ylabel="Cumulative share of eligible pairs (%)",ylim=(0,102))
    ax.set_xticks([0,1,10,100,1000]);ax.set_xticklabels(["0","1","10","100","1,000"])
    ax.yaxis.set_major_formatter(PercentFormatter());ax.text(.04,.1,f"{len(relative):,} nonzero-baseline pairs\n{int((mask & (a == 0)).sum()):,} zero-baseline pairs excluded",transform=ax.transAxes,fontsize=9)
    for ax in [axes[0,0],axes[1,0],axes[1,1]]:
        ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.16);ax.set_axisbelow(True)
    fig.text(.06,.045,"Pair totals include self pairs. Neuron movement uses optimal cluster-label matching.\nType-guided agreement is not independent biological validation; equal partitions do not mean equal matrices.",fontsize=10,color="#475569")
    fig.savefig(output,dpi=dpi,facecolor="white",bbox_inches="tight",pad_inches=.18);plt.close(fig)
    return {"renderer_version":VERSION,"path":str(output),"sha256":sha(output),"dpi":dpi,"plot_only":True,"relative_score_pairs":int(eligible.sum()),"zero_baseline_excluded":int((mask & (a==0)).sum())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    for name in ("folded", "reflected", "summary", "profile", "output"):
        parser.add_argument("--"+name, required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.folded, args.reflected, args.summary, args.profile, args.output), indent=2))


if __name__ == "__main__":
    main()
