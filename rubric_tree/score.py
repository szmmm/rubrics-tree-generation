"""Reference scorer (PLAN §5). It defines what the gates mean.

Branch: the raw pass rate of its leaves (WebDevJudge). A branch with no
leaves is skipped. The root is the mean of the branches that are left,
weighted by branch_weights when the record has them (re-normalized over those
branches), else unweighted. Remove branch_weights to mask them. A critical
leaf is a hard boundary: if one fails, the whole score is 0.
"""
from __future__ import annotations

from .schema import BRANCHES, leaves


def score(record: dict, passed: dict[str, bool]) -> dict:
    """``passed`` maps every leaf id to the judge's verdict."""
    tree = record["tree"]
    weights = record.get("branch_weights") or {b: 1 for b in BRANCHES}
    branches, failed_critical = {}, []
    for b in BRANCHES:
        results = [(leaf, passed[leaf["id"]]) for leaf in leaves(tree[b])]
        branches[b] = (sum(1 for _, ok in results if ok) / len(results)) if results else None
        failed_critical += [leaf["id"] for leaf, ok in results if leaf.get("critical") and not ok]
    live = {b: weights[b] for b in BRANCHES if branches[b] is not None}
    total = sum(w * branches[b] for b, w in live.items()) / sum(live.values())
    if failed_critical:
        total = 0.0
    return {"score": total, "branches": branches, "failed_critical": failed_critical}
