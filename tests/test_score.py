import pytest

from fakes import record
from rubric_tree.score import score


def _leaf(nid, weight=1, critical=False):
    return {"id": nid, "description": nid, "weight": weight, "critical": critical, "children": None}


def _record(content_children=None):
    return {
        "branch_weights": {"intention": 0.1, "content": 0.2, "static": 0.3, "dynamic": 0.4},
        "tree": {
            "intention": {"id": "I", "children": [_leaf("I.1")]},
            "content": {"id": "C", "children": content_children or []},
            "static": {"id": "S", "children": [
                {"id": "S.1", "weight": 3, "critical": False,
                 "children": [_leaf("S.1.1", 5), _leaf("S.1.2", 1)]},
                _leaf("S.2", 1)]},
            "dynamic": {"id": "D", "children": [
                {"id": "D.B", "weight": 1, "critical": False, "children": [_leaf("D.B.1")]},
                {"id": "D.C", "weight": 1, "critical": False,
                 "children": [_leaf("D.C.1", 5, critical=True), _leaf("D.C.2", 1)]}]},
        },
    }


ALL = ["I.1", "S.1.1", "S.1.2", "S.2", "D.B.1", "D.C.1", "D.C.2"]


def test_all_pass_scores_one():
    result = score(_record(), {i: True for i in ALL})
    assert result["score"] == pytest.approx(1.0)
    assert result["failed_critical"] == []


def test_group_is_the_weighted_mean_of_its_children():
    passed = {i: True for i in ALL} | {"S.1.2": False}
    result = score(_record(), passed)
    # S.1 = 5/6; S = (3 * 5/6 + 1 * 1) / 4
    assert result["branches"]["static"] == pytest.approx((3 * 5 / 6 + 1) / 4)


def test_failed_critical_child_sets_the_parent_to_zero():
    passed = {i: True for i in ALL} | {"D.C.1": False}
    result = score(_record(), passed)
    # D.C = 0 despite D.C.2 passing; D = (1 * 1 + 1 * 0) / 2
    assert result["branches"]["dynamic"] == pytest.approx(0.5)
    assert result["failed_critical"] == ["D.C.1"]


def test_empty_branch_is_skipped_and_weights_renormalized():
    passed = {i: True for i in ALL} | {"I.1": False}
    result = score(_record(), passed)
    assert result["branches"]["content"] is None
    # content (0.2) is skipped: (0.1 * 0 + 0.3 + 0.4) / 0.8
    assert result["score"] == pytest.approx(0.7 / 0.8)


def test_scores_a_generated_record():
    rec = record()
    from rubric_tree.schema import BRANCHES, leaves
    ids = [leaf["id"] for b in BRANCHES for leaf in leaves(rec["tree"][b])]
    assert score(rec, {i: True for i in ids})["score"] == pytest.approx(1.0)
    # the universal "page loads" leaf is critical: it zeroes the static branch
    result = score(rec, {i: i != "S.4" for i in ids})
    assert result["branches"]["static"] == 0.0 and result["failed_critical"] == ["S.4"]


def test_missing_verdict_is_an_error():
    with pytest.raises(KeyError):
        score(_record(), {"I.1": True})
