"""Shape statistics of rubric trees: leaves, depth, origin and verify_by mix."""
from __future__ import annotations

from collections import Counter

from .schema import BRANCHES, iter_nodes, leaves


def tree_stats(record: dict) -> dict:
    tree = record["tree"]
    all_leaves = [leaf for b in BRANCHES for leaf in leaves(tree[b])]
    return {
        "leaves": len(all_leaves),
        "leaves_by_branch": {b: len(leaves(tree[b])) for b in BRANCHES},
        "max_depth": max(d for b in BRANCHES for _, d in iter_nodes(tree[b])),
        "critical": sum(1 for b in BRANCHES for n, _ in iter_nodes(tree[b]) if n.get("critical")),
        "origin": dict(Counter(leaf["origin"] for leaf in all_leaves)),
        "verify_by": dict(Counter(leaf["verify_by"] for leaf in all_leaves)),
    }


def summary_table(records: list[dict]) -> str:
    """One row per record plus a mean row, as a Markdown table."""
    head = ["id", "method", "leaves", *BRANCHES, "depth", "critical",
            "explicit", "implicit", "archetype", "universal", "fact"]
    rows = []
    for r in records:
        s = tree_stats(r)
        rows.append([r["id"], r["method"], s["leaves"],
                     *(s["leaves_by_branch"][b] for b in BRANCHES), s["max_depth"],
                     s["critical"],
                     *(s["origin"].get(o, 0) for o in ("explicit", "implicit", "archetype", "universal")),
                     s["verify_by"].get("fact", 0)])
    if rows:
        rows.append(["mean", "", *(round(sum(row[i] for row in rows) / len(rows), 1)
                                   for i in range(2, len(head)))])
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)
