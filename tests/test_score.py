import pytest

from fakes import record
from rubric_tree.score import score


def _leaf(nid, critical=False):
    return {"id": nid, "description": nid, "critical": critical, "children": None}


def _record(content_children=None):
    return {
        "tree": {
            "intention": {"id": "I", "children": [_leaf("I.1")]},
            "content": {"id": "C", "children": content_children or []},
            "static": {"id": "S", "children": [
                {"id": "S.1", "critical": False,
                 "children": [_leaf("S.1.1"), _leaf("S.1.2")]},
                _leaf("S.2")]},
            "dynamic": {"id": "D", "children": [
                {"id": "D.B", "critical": False, "children": [_leaf("D.B.1")]},
                {"id": "D.C", "critical": False,
                 "children": [_leaf("D.C.1", critical=True), _leaf("D.C.2")]}]},
        },
    }


ALL = ["I.1", "S.1.1", "S.1.2", "S.2", "D.B.1", "D.C.1", "D.C.2"]


def test_all_pass_scores_one():
    result = score(_record(), {i: True for i in ALL})
    assert result["score"] == pytest.approx(1.0)
    assert result["failed_critical"] == []


def test_branch_is_the_raw_leaf_pass_rate():
    passed = {i: True for i in ALL} | {"S.1.2": False}
    result = score(_record(), passed)
    # 2 of the 3 static leaves pass; the group S.1 does not matter
    assert result["branches"]["static"] == pytest.approx(2 / 3)


def test_failed_critical_leaf_sets_the_whole_score_to_zero():
    passed = {i: True for i in ALL} | {"D.C.1": False}
    result = score(_record(), passed)
    # 2 of the 3 dynamic leaves pass, but the gate sets the total to 0
    assert result["branches"]["dynamic"] == pytest.approx(2 / 3)
    assert result["score"] == 0.0 and result["failed_critical"] == ["D.C.1"]


def test_branch_weights_are_used_when_present():
    passed = {i: True for i in ALL} | {"I.1": False}
    rec = _record() | {"branch_weights": {"intention": 0.1, "content": 0.2, "static": 0.3, "dynamic": 0.4}}
    # content (0.2) is skipped: (0.1 * 0 + 0.3 + 0.4) / 0.8
    assert score(rec, passed)["score"] == pytest.approx(0.7 / 0.8)


def test_empty_branch_is_skipped():
    passed = {i: True for i in ALL} | {"I.1": False}
    result = score(_record(), passed)
    assert result["branches"]["content"] is None
    # content is skipped: (0 + 1 + 1) / 3
    assert result["score"] == pytest.approx(2 / 3)


def test_scores_a_generated_record():
    rec = record()
    from rubric_tree.schema import BRANCHES, leaves
    ids = [leaf["id"] for b in BRANCHES for leaf in leaves(rec["tree"][b])]
    assert score(rec, {i: True for i in ids})["score"] == pytest.approx(1.0)
    # the universal "page loads" leaf is critical: it zeroes the whole score
    result = score(rec, {i: i != "S.4" for i in ids})
    assert result["score"] == 0.0 and result["failed_critical"] == ["S.4"]


def test_missing_verdict_is_an_error():
    with pytest.raises(KeyError):
        score(_record(), {"I.1": True})
