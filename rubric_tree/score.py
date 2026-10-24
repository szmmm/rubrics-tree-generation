"""Reference scorer (PLAN §5). It defines what the gates mean.

Gate, then flat rate. A critical leaf is a hard boundary: if one fails, the
whole score is 0. Else the score is the pass rate over all leaves of the tree;
every leaf has the same weight. Branches and groups do not change the score.
The per-branch pass rates are returned for diagnosis only.
"""
from __future__ import annotations

from .schema import BRANCHES, leaves


def score(record: dict, passed: dict[str, bool]) -> dict:
    """``passed`` maps every leaf id to the judge's verdict."""
    tree = record["tree"]
    branches, failed_critical, n_pass, n_all = {}, [], 0, 0
    for b in BRANCHES:
        results = [(leaf, passed[leaf["id"]]) for leaf in leaves(tree[b])]
        ok_count = sum(1 for _, ok in results if ok)
        branches[b] = (ok_count / len(results)) if results else None
        failed_critical += [leaf["id"] for leaf, ok in results if leaf.get("critical") and not ok]
        n_pass, n_all = n_pass + ok_count, n_all + len(results)
    total = 0.0 if failed_critical else n_pass / n_all
    return {"score": total, "branches": branches, "failed_critical": failed_critical}
