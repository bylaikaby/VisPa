"""Reusable legacy review profile execution.
Version: 0.1.3 (local/unreleased)
Last updated: 2026-11-18
Change history: ../../../CHANGELOG.md
- 2026-11-18: Preserve legacy square-root-fraction Euclidean projection diagnostic; cosine retained as explicitly separate sensitivity.
- 2026-11-18: Reuse fixed-matrix stability with explicit legacy linkage, monkey holdouts and projection cosine silhouette.
- 2026-11-18: Explicit known_only versus legacy_label unknown-type penalty policy.
- 2026-11-18: Execute explicit legacy clustering profiles without changing FNT production.
Status: candidate
"""
import json
from pathlib import Path
import numpy as np
from scipy.cluster.hierarchy import fcluster
from .fnt_pipeline import analysis_matrix, hierarchy


def load_profile(path):
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    if profile.get("schema") != "remap.clustering_review_profile.v1":
        raise ValueError("Unknown review profile schema")
    c = profile["clustering"]
    if c["score_mode"] != "raw" or c["representation"] != "spearman_profile" or c["linkage"] != "ward_d2":
        raise ValueError("This profile executor preserves raw-score Spearman/Ward.D2 semantics")
    ks = c["candidate_k"]
    if not ks or any(type(k) is not int or k < 2 for k in ks) or len(ks) != len(set(ks)):
        raise ValueError("candidate_k must contain unique integers >=2")
    penalties = profile["comparators"]["penalty_factors"]
    if not penalties or any(not np.isfinite(p) or p < 0 for p in penalties):
        raise ValueError("Invalid type penalties")
    if c["penalty_absolute"] != 0 or c["penalty_factor"] not in penalties:
        raise ValueError("Baseline must be a declared factor comparator; absolute penalty unsupported")
    if c["display_k"] not in ks or profile["plots"]["boundaries_k"] != c["display_k"]:
        raise ValueError("Plot boundaries must use the declared display cut")
    if c.get("unknown_type_policy", "legacy_label") not in ("legacy_label", "known_only"):
        raise ValueError("Unknown type-penalty policy")
    return profile


def fit_profile(raw, types, profile):
    """Reuse existing distance/linkage functions; return trees and all declared cuts."""
    raw = np.asarray(raw, dtype=float)
    if len(types) != len(raw) or any(not isinstance(t, str) or not t.strip() for t in types):
        raise ValueError("Explicit aligned nonempty type labels required")
    c = profile["clustering"]
    if max(c["candidate_k"]) >= len(raw):
        raise ValueError("Candidate cuts must be smaller than cohort size")
    policy = c.get("unknown_type_policy", "legacy_label")
    if policy not in ("legacy_label", "known_only"):
        raise ValueError("Unknown type-penalty policy")
    base = analysis_matrix(raw, c["representation"], 0, list(types))
    labels = np.asarray(types)
    unlike = labels[:, None] != labels[None, :]
    if policy == "known_only":
        known = ~np.isin(labels, c.get("unknown_type_labels", ["Unclassified", "Unknown"]))
        unlike &= known[:, None] & known[None, :]
    result = {}
    for penalty in profile["comparators"]["penalty_factors"]:
        distance = base + penalty * base.max() * unlike
        tree = hierarchy(distance, c["linkage"])
        result[penalty] = {"distance": distance, "tree": tree,
                           "cuts": {k: fcluster(tree, k, criterion="maxclust") for k in c["candidate_k"]}}
    return result


def evaluate_profile(fits, profile, animals, projection_fractions):
    """Fixed-matrix stability plus descriptive projection and animal diagnostics.

    Leave-one-animal-out sensitivity reclusters remaining neurons; it does not
    measure prediction on an unseen animal or establish biological acceptance.
    """
    import pandas as pd
    from scipy.spatial.distance import pdist, squareform
    from sklearn.metrics import silhouette_score
    from .clustering_validation import evaluate_k
    fractions = np.asarray(projection_fractions, dtype=float)
    if fractions.ndim != 2 or not np.isfinite(fractions).all() or np.any(fractions < 0):
        raise ValueError("Invalid projection fractions")
    if not np.allclose(fractions.sum(axis=1), 1):
        raise ValueError("Projection fractions must use complete bilateral totals")
    legacy_projection_distance = squareform(pdist(np.sqrt(fractions), metric="euclidean"))
    projection_distance = squareform(pdist(fractions, metric="cosine"))
    projection_distance = np.clip(projection_distance, 0, 2)
    settings = profile["stability"]
    diagnostics, stability, holdouts = [], [], []
    for penalty, fit in fits.items():
        metrics, labels, per_cluster, held = evaluate_k(
            fit["distance"], profile["clustering"]["candidate_k"],
            repeats=settings["repeats"], fraction=settings["fraction"], seed=settings["seed"],
            groups=animals, linkage_builder=lambda d: hierarchy(d, profile["clustering"]["linkage"]))
        for k, cut in labels.items():
            if not np.array_equal(cut, fit["cuts"][k]):
                raise ValueError("Diagnostic hierarchy differs from fitted hierarchy")
            metrics.loc[metrics.requested_k == k, "projection_sqrt_euclidean_silhouette"] = (
                silhouette_score(legacy_projection_distance, cut, metric="precomputed")
                if 1 < len(np.unique(cut)) < len(cut) else np.nan)
            metrics.loc[metrics.requested_k == k, "projection_cosine_silhouette"] = (
                silhouette_score(projection_distance, cut, metric="precomputed")
                if 1 < len(np.unique(cut)) < len(cut) else np.nan)
            frame = per_cluster[k].assign(penalty_factor=penalty, requested_k=k)
            stability.append(frame)
        diagnostics.append(metrics.assign(penalty_factor=penalty))
        holdouts.append(held.assign(penalty_factor=penalty))
    return pd.concat(diagnostics, ignore_index=True), pd.concat(stability, ignore_index=True), pd.concat(holdouts, ignore_index=True)
