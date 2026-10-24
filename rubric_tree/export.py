"""Convert records to the WebDevJudge rubric format and to Markdown for review."""
from __future__ import annotations

from .schema import BRANCHES, is_leaf


def webdevjudge_tree(tree: dict) -> dict:
    """Our four-branch tree as a WebDevJudge tree: only description and
    children, and the content branch merged into static as one group."""
    static = _strip(tree["static"])
    if tree["content"]["children"]:
        static["children"].append(_strip(tree["content"]))
    return {"intention": _strip(tree["intention"]), "static": static,
            "dynamic": _strip(tree["dynamic"])}


def to_webdevjudge(record: dict) -> dict:
    """One line of a WebDevJudge rubric file."""
    return {"question_id": record["id"], "rubric_tree": webdevjudge_tree(record["tree"])}


def from_webdevjudge(wdj: dict) -> dict:
    """A WebDevJudge tree in our schema, for the baseline method: empty content,
    nothing critical, every leaf explicit with no covers."""
    return {"intention": _convert(wdj["intention"], "intention", root=True),
            "content": {"description": "内容", "children": []},
            "static": _convert(wdj["static"], "static", root=True),
            "dynamic": _convert(wdj["dynamic"], "dynamic", root=True)}


def _strip(node: dict) -> dict:
    children = node["children"]
    return {"description": node["description"],
            "children": None if children is None else [_strip(c) for c in children]}


def _convert(node: dict, branch: str, *, root: bool = False) -> dict:
    out = {"description": node["description"]}
    if not root:
        out.update(critical=False)
    if node["children"] is None:
        out.update(origin="explicit", covers=[],
                   verify_by="interaction" if branch == "dynamic" else "view")
    out["children"] = (None if node["children"] is None
                       else [_convert(c, branch) for c in node["children"]])
    return out


def to_markdown(records: list[dict]) -> str:
    """All records as one Markdown file for a person to read and review."""
    return "\n\n---\n\n".join(_record_markdown(r) for r in records) + "\n"


def _record_markdown(record: dict) -> str:
    lines = [f"## {record['id']} · {record['method']}", "", f"> {record['prompt']}", ""]
    spec = record.get("spec")
    if spec:
        frame = spec.get("time_frame") or {}
        lines += [f"**Spec.** archetypes: {', '.join(spec['archetypes'])} · "
                  f"delivery: {spec['delivery']} · design_focus: {spec['design_focus']} · "
                  f"user's today: {frame.get('date', record.get('as_of'))}"
                  + (f" · about: {frame['refers_to']}" if frame.get("refers_to") else ""), ""]
        if frame.get("evidence_quote"):
            lines.append(f"- time: not as_of {record.get('as_of')} — “{frame['evidence_quote']}”, "
                         f"because: {frame.get('rationale')}")
        for req in spec["requirements"]:
            why = (f"“{req['evidence_quote']}”" if req["type"] == "explicit"
                   else f"because: {req['rationale']}")
            lines.append(f"- {req['id']} ({req['type']}{', critical' if req['critical'] else ''}) "
                         f"{req['text']} — {why}")
        for need in spec["knowledge_needs"]:
            sure = "confident" if need["generator_confident"] else "NOT confident"
            lines.append(f"- knowledge: {need['topic']} ({sure})")
        lines.append("")
    for branch in BRANCHES:
        lines += _node_markdown(record["tree"][branch], 0)
    return "\n".join(lines)


def _node_markdown(node: dict, depth: int) -> list[str]:
    pad = "  " * depth
    if depth == 0:
        head = f"- **{node['id']}** {node['description']}"
    elif is_leaf(node):
        tags = ["**critical**"] if node["critical"] else []
        tags += [node["origin"] + (" " + ",".join(node["covers"]) if node["covers"] else ""),
                 node["verify_by"]]
        head = f"- `{node['id']}` [{' · '.join(tags)}] {node['description']}"
        if node.get("note"):
            head += f" — _{node['note']}_"
    else:
        crit = " [**critical**]" if node["critical"] else ""
        head = f"- `{node['id']}`{crit} **{node['description']}**"
    lines = [pad + head]
    for child in node["children"] or []:
        lines += _node_markdown(child, depth + 1)
    return lines
