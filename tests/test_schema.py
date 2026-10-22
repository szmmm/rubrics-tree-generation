import pytest

from fakes import leaf, node, record
from rubric_tree import archetypes, pipeline, prompts, schema


def test_valid_record_passes():
    assert schema.validate(record()) == []


def test_worked_example_passes_the_validator():
    tree = pipeline._prepare(prompts.EXAMPLE_TREE, archetypes.universal_leaves(prompts.EXAMPLE_SPEC))
    rec = {"prompt": prompts.EXAMPLE_QUERY, "spec": prompts.EXAMPLE_SPEC, "tree": tree,
           "branch_weights": pipeline._normalize_weights(prompts.EXAMPLE_DRAFT["branch_weight_proposal"])}
    assert schema.validate(rec) == []


def test_assign_ids_uses_path_form():
    ids = [n["id"] for b in schema.BRANCHES for n, _ in schema.iter_nodes(record()["tree"][b])]
    assert ids == ["I", "I.1", "I.2", "I.3", "C", "C.1", "C.2",
                   "S", "S.1", "S.1.1", "S.1.2", "S.2", "S.3", "S.4", "S.5", "S.6",
                   "D", "D.B", "D.B.1", "D.B.2", "D.B.3", "D.C", "D.C.1", "D.C.2"]


def test_normalize_tree():
    tree = schema.normalize_tree({
        "intention": {"children": [{"weight": 2, "description": "x", "extra": 1, "children": []}],
                      "description": "root"},
        "content": {"description": "c", "children": []},
    })
    child = tree["intention"]["children"][0]
    assert list(child) == ["description", "critical", "covers", "children"]
    assert child["children"] is None and child["critical"] is False
    assert tree["content"]["children"] == []     # an empty branch root stays a group


def _deepen(rec):
    n = leaf("五层深的检查")
    for _ in range(4):
        n = {"description": "分组", "critical": False, "children": [n]}
    rec["tree"]["static"]["children"].append(n)


def _drop_branch(rec):
    del rec["tree"]["content"]


def _many_critical(rec):
    for nid in ("I.1", "I.2", "I.3", "C.1", "C.2"):
        node(rec, nid)["critical"] = True


def _extra_requirement(rec):
    rec["spec"]["requirements"].append(
        {"id": "R5", "type": "implicit", "text": "x", "rationale": "y", "critical": False})


def _too_many_leaves(rec):
    rec["tree"]["intention"]["children"] += [leaf(f"多余{i}") for i in range(30)]


# (name, mutation, part of the expected error) — one failing fixture per rule.
CASES = [
    ("missing branch", _drop_branch, "tree must have exactly the branches"),
    ("critical type", lambda r: node(r, "S.2").update(critical="yes"), "S.2: critical must be"),
    ("empty description", lambda r: node(r, "S.2").update(description=" "), "S.2: description"),
    ("children type", lambda r: node(r, "S.1").update(children="x"), "S.1: children must be"),
    ("empty group", lambda r: node(r, "S.1").update(children=[]), "S.1: a group must have"),
    ("root is a leaf", lambda r: r["tree"]["intention"].update(children=None),
     "I: a branch root must have a children list"),
    ("dynamic has two groups",
     lambda r: r["tree"]["dynamic"].update(children=r["tree"]["dynamic"]["children"][:1]),
     "dynamic must have exactly two groups"),
    ("content empty", lambda r: r["tree"]["content"].update(children=[]),
     "content is empty, but spec.knowledge_needs is not"),
    ("too few leaves", lambda r: [r["tree"]["static"]["children"].pop(0) for _ in range(2)],
     "tree has 14 leaves"),
    ("too many leaves", _too_many_leaves, "tree has 47 leaves"),
    ("weights sum", lambda r: r["branch_weights"].update(intention=0.5), "must sum to 1"),
    ("critical leaf without critical requirement", lambda r: node(r, "S.2").update(critical=True),
     "S.2: a critical leaf must cover a critical requirement"),
    ("critical group", lambda r: node(r, "S.1").update(critical=True), "S.1: a group must not be critical"),
    ("too deep", _deepen, "leaf is 5 levels below the branch root"),
    ("requirement not covered", _extra_requirement, "R5 is not covered"),
    ("unknown covers id", lambda r: node(r, "S.2").update(covers=["R9"]), "unknown requirement 'R9'"),
    ("covers type", lambda r: node(r, "S.2").update(covers="R2"), "S.2: covers must be a list"),
    ("explicit leaf without covers", lambda r: node(r, "S.2").update(covers=[]),
     "S.2: an explicit leaf must list"),
    ("evidence quote", lambda r: r["spec"]["requirements"][0].update(evidence_quote="没说过的话"),
     "is not an exact substring of the query"),
    ("dynamic verify_by", lambda r: node(r, "D.B.1").update(verify_by="view"),
     "D.B.1: a leaf under dynamic must have verify_by"),
    ("origin enum", lambda r: node(r, "S.2").update(origin="guess"), "S.2: origin must be one of"),
    ("verify_by enum", lambda r: node(r, "S.2").update(verify_by="smell"), "S.2: verify_by must be"),
    ("note type", lambda r: node(r, "S.2").update(note=3), "S.2: note must be a string"),
    ("too many critical", _many_critical, "tree has 7 critical nodes; max 5"),
    ("critical root", lambda r: r["tree"]["static"].update(critical=True),
     "S: a branch root must not be critical"),
    ("duplicate description", lambda r: node(r, "S.2").update(description="能记录 喝水！"),
     "S.2: same description as I.1"),
    ("duplicate id", lambda r: node(r, "S.2").update(id="S.3"), "id 'S.3' is not unique"),
]


@pytest.mark.parametrize("name,mutate,expected", CASES, ids=[c[0] for c in CASES])
def test_each_rule_has_a_failing_fixture(name, mutate, expected):
    rec = record()
    mutate(rec)
    errors = schema.validate(rec)
    assert any(expected in e for e in errors), errors


SPEC_CASES = [
    ("archetypes", lambda s: s.update(archetypes=["shop"]), "spec.archetypes must list"),
    ("delivery", lambda s: s.update(delivery="desktop"), "spec.delivery"),
    ("ui_language", lambda s: s.update(ui_language=""), "spec.ui_language"),
    ("design_focus", lambda s: s.update(design_focus="no"), "spec.design_focus"),
    ("requirements", lambda s: s.update(requirements=[]), "spec.requirements must be a non-empty"),
    ("requirement id", lambda s: s["requirements"][1].update(id="R1"), "id must be a unique"),
    ("requirement critical", lambda s: s["requirements"][0].update(critical=5), "critical must be"),
    ("type", lambda s: s["requirements"][0].update(type="stated"), "type must be explicit"),
    ("rationale", lambda s: s["requirements"][3].pop("rationale"), "needs a rationale"),
    ("knowledge need", lambda s: s["knowledge_needs"][0].update(generator_confident="yes"),
     "spec.knowledge_needs[0] needs"),
]


@pytest.mark.parametrize("name,mutate,expected", SPEC_CASES, ids=[c[0] for c in SPEC_CASES])
def test_spec_rules(name, mutate, expected):
    rec = record()
    mutate(rec["spec"])
    errors = schema.validate_spec(rec["spec"], rec["prompt"])
    assert any(expected in e for e in errors), errors


def test_evidence_quote_ignores_whitespace():
    rec = record()
    rec["spec"]["requirements"][0]["evidence_quote"] = "记录 每天 喝水量"
    assert schema.validate_spec(rec["spec"], rec["prompt"]) == []


def test_empty_content_is_valid_without_knowledge_needs():
    rec = record()
    rec["spec"]["knowledge_needs"] = []
    rec["tree"]["content"]["children"] = []
    rec["tree"]["intention"]["children"] += [leaf("补充1"), leaf("补充2")]   # keep 16 leaves
    schema.assign_ids(rec["tree"])
    assert schema.validate(rec) == []


WDJ_CASES = [
    ("keys", lambda t: t.pop("static"), "top-level keys"),
    ("node shape", lambda t: t["static"]["children"].append({"description": "x"}),
     "needs description and children"),
    ("description", lambda t: t["intention"]["children"][0].update(description=""), "description"),
    ("children type", lambda t: t["intention"]["children"][0].update(children="x"), "list or null"),
    ("empty branch", lambda t: t["static"].update(children=[]), "static: children must be a non-empty"),
    ("dynamic size", lambda t: t["dynamic"]["children"].append({"description": "x", "children": None}),
     "exactly two children"),
]


@pytest.mark.parametrize("name,mutate,expected", WDJ_CASES, ids=[c[0] for c in WDJ_CASES])
def test_webdevjudge_errors(name, mutate, expected):
    from rubric_tree.export import webdevjudge_tree
    wdj = webdevjudge_tree(record()["tree"])
    assert schema.webdevjudge_errors(wdj) == []
    mutate(wdj)
    errors = schema.webdevjudge_errors(wdj)
    assert any(expected in e for e in errors), errors
