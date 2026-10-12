"""Reference scorer (PLAN §5). It defines what the weights and gates mean.

Leaf: 1 if it passes, else 0. Group: 0 if a critical child scores 0, else
the weighted mean of its children (weights relative to siblings). A group or
branch with no leaves is skipped. The root is the mean of the branches,
weighted by branch_weights and re-normalized over the branches that are left.
"""
from __future__ import annotations

from .schema import BRANCHES, leaves


def score(record: dict, passed: dict[str, bool]) -> dict:
    """``passed`` maps every leaf id to the judge's verdict."""
    tree, weights = record["tree"], record["branch_weights"]
    branches = {b: _score(tree[b], passed) for b in BRANCHES}
    live = {b: weights[b] for b in BRANCHES if branches[b] is not None}
    total = sum(w * branches[b] for b, w in live.items()) / sum(live.values())
    failed_critical = [leaf["id"] for b in BRANCHES for leaf in leaves(tree[b])
                       if leaf.get("critical") and not passed[leaf["id"]]]
    return {"score": total, "branches": branches, "failed_critical": failed_critical}


def _score(node: dict, passed: dict[str, bool]) -> float | None:
    if node["children"] is None:
        return 1.0 if passed[node["id"]] else 0.0
    scored = [(c, s) for c in node["children"] if (s := _score(c, passed)) is not None]
    if not scored:
        return None
    if any(c.get("critical") and s == 0 for c, s in scored):
        return 0.0
    return sum(c["weight"] * s for c, s in scored) / sum(c["weight"] for c, _ in scored)
