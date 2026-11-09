"""The rubric record: tree helpers, id assignment and the validators (PLAN §3, §4.6).

Records and trees stay plain dicts, in the same shape as the JSON on disk. A
node is a group when "children" is a list, and a leaf when it is null.
"""
from __future__ import annotations

import re

from .archetypes import ARCHETYPE_IDS, LANGUAGES

BRANCHES = ("intention", "content", "static", "dynamic")
BRANCH_IDS = {"intention": "I", "content": "C", "static": "S", "dynamic": "D"}
DYNAMIC_CHILD_IDS = ("D.B", "D.C")    # basic, then complex

REQUIREMENT_TYPES = ("explicit", "implicit", "attractive")
ORIGINS = (*REQUIREMENT_TYPES, "archetype", "universal")
VERIFY_BY = ("view", "interaction", "fact")
DELIVERIES = ("mobile_app", "single_page", "unspecified")

MIN_LEAVES, MAX_LEAVES = 15, 40
MAX_DEPTH = 4          # levels below a branch root
MAX_ATTRACTIVE = 4     # attractive requirements per spec, and attractive leaves per tree

# Keys a node can carry, in the order they are written. "support" exists only
# between the merge and the final record.
_KEY_ORDER = ("id", "description", "critical", "origin", "covers",
              "verify_by", "note", "support", "children")

_WDJ_BRANCHES = ("intention", "static", "dynamic")
_LEAF_KEYS = ("origin", "covers", "verify_by")


def is_leaf(node: dict) -> bool:
    return node.get("children") is None


def iter_nodes(node: dict, depth: int = 0):
    """(node, depth) for the node and all nodes below it."""
    yield node, depth
    for child in node.get("children") or []:
        yield from iter_nodes(child, depth + 1)


def leaves(node: dict) -> list[dict]:
    return [n for n, _ in iter_nodes(node) if is_leaf(n)]


def normalize_tree(tree):
    """Bring an LLM-written tree into the canonical key order and shape.

    A non-root node with an empty children list becomes a leaf if it has a
    leaf key (origin, covers, verify_by); else it stays an empty group, which
    the validator reports. Missing "critical" is false, and missing leaf
    "covers" is empty. Unknown keys go. Everything else stays for the
    validator to judge.
    """
    if not isinstance(tree, dict):
        return tree
    return {b: _normalize(node, root=True) if b in BRANCHES else node
            for b, node in tree.items()}


def _normalize(node, *, root: bool = False):
    if not isinstance(node, dict):
        return node
    node = dict(node)
    children = node.get("children")
    if children == [] and not root and any(k in node for k in _LEAF_KEYS):
        children = None
    node["children"] = ([_normalize(c) for c in children]
                        if isinstance(children, list) else children)
    if not root:
        node.setdefault("critical", False)
    if node["children"] is None:
        node.setdefault("covers", [])
    return {k: node[k] for k in _KEY_ORDER if k in node}


def assign_ids(tree: dict) -> dict:
    """Give every node its path id: I, I.1, C.2.3, D.B.1, D.C.4."""
    for branch in BRANCHES:
        if isinstance(tree.get(branch), dict):
            _assign(tree[branch], BRANCH_IDS[branch])
    return tree


def _assign(node: dict, node_id: str) -> None:
    node["id"] = node_id
    node.update({k: node.pop(k) for k in _KEY_ORDER[1:] if k in node})
    children = node.get("children")
    if not isinstance(children, list):
        return
    for i, child in enumerate(children, 1):
        if not isinstance(child, dict):
            continue
        if node_id == "D" and i <= len(DYNAMIC_CHILD_IDS):
            _assign(child, DYNAMIC_CHILD_IDS[i - 1])
        else:
            _assign(child, f"{node_id}.{i}")


# ── validation ────────────────────────────────────────────────────────────

def validate_spec(spec, query: str, as_of: str | None = None) -> list[str]:
    """Errors in the stage-1 query analysis. Without as_of, time_frame.date
    is only checked for its form."""
    if not isinstance(spec, dict):
        return ["spec must be a JSON object"]
    errors = []
    archetypes = spec.get("archetypes")
    if not (isinstance(archetypes, list) and 1 <= len(archetypes) <= 3
            and all(a in ARCHETYPE_IDS for a in archetypes)):
        errors.append(f"spec.archetypes must list 1-3 of {', '.join(ARCHETYPE_IDS)}; "
                      f"got {archetypes!r}")
    if spec.get("delivery") not in DELIVERIES:
        errors.append(f"spec.delivery must be one of {', '.join(DELIVERIES)}")
    if spec.get("ui_language") not in LANGUAGES:
        errors.append(f"spec.ui_language must be one of {', '.join(LANGUAGES)}")
    if not isinstance(spec.get("design_focus"), bool):
        errors.append("spec.design_focus must be true or false")

    frame = spec.get("time_frame")
    day = frame.get("date") if isinstance(frame, dict) else None
    if not (isinstance(day, str) and re.fullmatch(r"\d{4}(-\d{2}){0,2}", day)):
        errors.append('spec.time_frame.date must be "YYYY", "YYYY-MM" or "YYYY-MM-DD"; '
                      f"got {day!r}")
    elif as_of is not None and day != as_of:
        quote = frame.get("evidence_quote")
        if not _text(quote) or _squeeze(quote) not in _squeeze(query):
            errors.append(f"spec.time_frame: date {day} is not as_of ({as_of}), so its "
                          f"evidence_quote {quote!r} must be an exact substring of the query")
        if not _text(frame.get("rationale")):
            errors.append(f"spec.time_frame: date {day} is not as_of ({as_of}), so it "
                          "needs a rationale")
    if isinstance(frame, dict) and "refers_to" in frame and not _text(frame["refers_to"]):
        errors.append("spec.time_frame.refers_to must be a non-empty string when present")

    requirements = spec.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        errors.append("spec.requirements must be a non-empty list")
        requirements = []
    seen = set()
    for i, req in enumerate(requirements):
        if not isinstance(req, dict):
            errors.append(f"spec.requirements[{i}] must be an object")
            continue
        rid = req.get("id")
        if not (isinstance(rid, str) and re.fullmatch(r"R\d+", rid)) or rid in seen:
            errors.append(f"spec.requirements[{i}]: id must be a unique R<number>; got {rid!r}")
        seen.add(rid)
        where = f"spec requirement {rid}"
        if not _text(req.get("text")):
            errors.append(f"{where}: text must be a non-empty string")
        if not isinstance(req.get("critical"), bool):
            errors.append(f"{where}: critical must be true or false")
        if req.get("type") == "explicit":
            quote = req.get("evidence_quote")
            if not _text(quote) or _squeeze(quote) not in _squeeze(query):
                errors.append(f"{where}: evidence_quote {quote!r} is not an exact "
                              "substring of the query")
        elif req.get("type") in ("implicit", "attractive"):
            if not _text(req.get("rationale")):
                errors.append(f"{where}: an {req['type']} requirement needs a rationale")
            if req["type"] == "attractive" and req.get("critical") is True:
                errors.append(f"{where}: an attractive requirement must not be critical")
        else:
            errors.append(f"{where}: type must be one of {', '.join(REQUIREMENT_TYPES)}")
    n_attractive = sum(1 for r in requirements
                       if isinstance(r, dict) and r.get("type") == "attractive")
    if n_attractive > MAX_ATTRACTIVE:
        errors.append(f"spec has {n_attractive} attractive requirements; max {MAX_ATTRACTIVE}")

    needs = spec.get("knowledge_needs")
    if not isinstance(needs, list):
        errors.append("spec.knowledge_needs must be a list")
        needs = []
    for i, need in enumerate(needs):
        if not (isinstance(need, dict) and _text(need.get("topic"))
                and isinstance(need.get("generator_confident"), bool)):
            errors.append(f"spec.knowledge_needs[{i}] needs topic and "
                          "generator_confident (bool)")
    return errors


def validate(record: dict) -> list[str]:
    """Errors in a full-method record. An empty list means valid."""
    spec = record.get("spec")
    errors = validate_spec(spec, record.get("prompt", ""), record.get("as_of"))
    tree = record.get("tree")
    if not isinstance(tree, dict) or set(tree) != set(BRANCHES):
        return errors + [f"tree must have exactly the branches {', '.join(BRANCHES)}"]

    found: list[tuple[dict, int]] = []    # (node, depth) of every node
    for branch in BRANCHES:
        errors += _check_node(tree[branch], branch, 0, found)

    dynamic = tree["dynamic"]
    if isinstance(dynamic, dict) and isinstance(dynamic.get("children"), list):
        groups = dynamic["children"]
        if len(groups) != 2 or not all(
                isinstance(g, dict) and isinstance(g.get("children"), list) for g in groups):
            errors.append("D: dynamic must have exactly two groups: basic (D.B), "
                          "then complex (D.C)")

    spec = spec if isinstance(spec, dict) else {}
    content = tree["content"]
    if isinstance(content, dict) and content.get("children") == [] and spec.get("knowledge_needs"):
        errors.append("C: content is empty, but spec.knowledge_needs is not")

    nodes = [n for n, _ in found]
    all_leaves = [n for n in nodes if is_leaf(n)]
    if not MIN_LEAVES <= len(all_leaves) <= MAX_LEAVES:
        errors.append(f"tree has {len(all_leaves)} leaves; it needs "
                      f"{MIN_LEAVES}-{MAX_LEAVES}")

    ids = [n.get("id") for n in nodes]
    for dup in sorted({i for i in ids if ids.count(i) > 1}, key=str):
        errors.append(f"id {dup!r} is not unique")
    by_text: dict[str, str] = {}
    for leaf in all_leaves:
        key = re.sub(r"[\W_]+", "", str(leaf.get("description", ""))).lower()
        if key in by_text:
            errors.append(f"{leaf.get('id')}: same description as {by_text[key]}")
        by_text.setdefault(key, leaf.get("id"))

    requirements = [r for r in spec.get("requirements") or [] if isinstance(r, dict)]
    known = {r.get("id") for r in requirements}
    covered = set()
    for leaf in all_leaves:
        covers = leaf.get("covers")
        if isinstance(covers, list):
            covered.update(covers)
            for rid in covers:
                if rid not in known:
                    errors.append(f"{leaf.get('id')}: covers unknown requirement {rid!r}")
    for req in requirements:
        if req.get("id") not in covered:
            errors.append(f"spec requirement {req.get('id')} is not covered by any leaf")
    critical_reqs = {r.get("id") for r in requirements if r.get("critical") is True}
    for leaf in all_leaves:
        if (leaf.get("critical") is True and leaf.get("origin") != "universal"
                and not critical_reqs & set(leaf.get("covers") or [])):
            errors.append(f"{leaf.get('id')}: a critical leaf must cover a critical requirement")

    # An attractive leaf covers only attractive requirements, and only it covers
    # them, so the leaf cap is the weight cap.
    attractive_reqs = {r.get("id") for r in requirements if r.get("type") == "attractive"}
    for leaf in all_leaves:
        covers = set(leaf.get("covers") or []) if isinstance(leaf.get("covers"), list) else set()
        if leaf.get("origin") == "attractive":
            if leaf.get("critical") is True:
                errors.append(f"{leaf.get('id')}: an attractive leaf must not be critical")
            if not covers <= attractive_reqs:
                errors.append(f"{leaf.get('id')}: an attractive leaf must cover only "
                              "attractive requirements")
        elif covers & attractive_reqs:
            errors.append(f"{leaf.get('id')}: a leaf that covers an attractive requirement "
                          "must have origin \"attractive\"")
    n_attractive = sum(1 for leaf in all_leaves if leaf.get("origin") == "attractive")
    if n_attractive > MAX_ATTRACTIVE:
        errors.append(f"tree has {n_attractive} attractive leaves; max {MAX_ATTRACTIVE}")
    return errors


def _check_node(node, branch: str, depth: int, found: list) -> list[str]:
    if not isinstance(node, dict):
        return [f"{branch}: every node must be a JSON object"]
    found.append((node, depth))
    nid = node.get("id") or branch
    errors = []
    if not _text(node.get("description")):
        errors.append(f"{nid}: description must be a non-empty string")
    if depth == 0:
        if node.get("critical"):
            errors.append(f"{nid}: a branch root must not be critical")
    else:
        if not isinstance(node.get("critical"), bool):
            errors.append(f"{nid}: critical must be true or false")

    children = node.get("children")
    if depth > 0 and children is not None and node.get("critical") is True:
        errors.append(f"{nid}: a group must not be critical; only a leaf can be critical")
    if children is None:
        if depth == 0:
            return errors + [f"{nid}: a branch root must have a children list"]
        return errors + _check_leaf(node, branch, depth)
    if not isinstance(children, list):
        return errors + [f"{nid}: children must be a list or null"]
    if not children and not (depth == 0 and branch == "content"):
        hint = {"D.B": "; write a single-step interaction leaf for it",
                "D.C": "; write a multi-step interaction leaf for it"}.get(nid, "")
        errors.append(f"{nid}: a group must have at least one child{hint}")
    for child in children:
        errors += _check_node(child, branch, depth + 1, found)
    return errors


def _check_leaf(leaf: dict, branch: str, depth: int) -> list[str]:
    nid = leaf.get("id") or branch
    errors = []
    if depth > MAX_DEPTH:
        errors.append(f"{nid}: leaf is {depth} levels below the branch root; max {MAX_DEPTH}")
    origin = leaf.get("origin")
    if origin not in ORIGINS:
        errors.append(f"{nid}: origin must be one of {', '.join(ORIGINS)}")
    if leaf.get("verify_by") not in VERIFY_BY:
        errors.append(f"{nid}: verify_by must be one of {', '.join(VERIFY_BY)}")
    elif branch == "dynamic" and leaf["verify_by"] != "interaction":
        errors.append(f"{nid}: a leaf under dynamic must have verify_by \"interaction\"")
    covers = leaf.get("covers")
    if not (isinstance(covers, list) and all(isinstance(c, str) for c in covers)):
        errors.append(f"{nid}: covers must be a list of requirement ids")
    elif origin in REQUIREMENT_TYPES and not covers:
        errors.append(f"{nid}: an {origin} leaf must list the requirement ids it covers")
    if "note" in leaf and not isinstance(leaf["note"], str):
        errors.append(f"{nid}: note must be a string")
    return errors


def webdevjudge_errors(tree) -> list[str]:
    """The WebDevJudge structure check (process_rubric.verify_tree_structure),
    with reasons instead of a bool. Used for the baseline method."""
    if not isinstance(tree, dict) or set(tree) != set(_WDJ_BRANCHES):
        return ["top-level keys must be exactly intention, static, dynamic"]
    errors = []
    for branch in _WDJ_BRANCHES:
        errors += _wdj_node_errors(tree[branch], branch)
        if not (isinstance(tree[branch], dict)
                and isinstance(tree[branch].get("children"), list)
                and tree[branch]["children"]):
            errors.append(f"{branch}: children must be a non-empty list")
    dynamic = tree["dynamic"]
    if (isinstance(dynamic, dict) and isinstance(dynamic.get("children"), list)
            and len(dynamic["children"]) != 2):
        errors.append("dynamic must have exactly two children: basic, then complex")
    return errors


def _wdj_node_errors(node, path: str) -> list[str]:
    if not isinstance(node, dict) or "description" not in node or "children" not in node:
        return [f"{path}: every node needs description and children"]
    errors = []
    if not _text(node["description"]):
        errors.append(f"{path}: description must be a non-empty string")
    children = node["children"]
    if children is not None and not isinstance(children, list):
        return errors + [f"{path}: children must be a list or null"]
    for i, child in enumerate(children or [], 1):
        errors += _wdj_node_errors(child, f"{path}.{i}")
    return errors


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _int_in(value, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _squeeze(text: str) -> str:
    return re.sub(r"\s+", "", text)
