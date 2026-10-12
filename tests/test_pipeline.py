import asyncio
import json

import pytest

from fakes import CASE, FakeLLM, draft, leaf, spec, tree
from rubric_tree import pipeline, schema
from rubric_tree.export import to_webdevjudge

NO_ISSUES = {"issues": []}
BLOCKING = {"issues": [{"leaf_id": "S.2", "type": "subjective", "severity": "blocking",
                        "fix": "make it observable"}]}


def _run(llm, tmp_path, **options):
    opts = pipeline.Options(as_of="2026-10-12", **options)
    result = asyncio.run(pipeline.run_all(llm, [CASE], tmp_path / "run", opts))
    return result, tmp_path / "run"


def _merged(with_support=True, extra_leaf=None):
    t = tree()
    if extra_leaf:
        t["static"]["children"].append(extra_leaf)
    if with_support:
        for branch in schema.BRANCHES:
            for leaf_node in schema.leaves(t[branch]):
                leaf_node["support"] = 2
    return {"tree": t}


def _final(run_dir):
    return json.loads((run_dir / "cases" / CASE["id"] / "final.json").read_text())


def _universal(record):
    return [n["description"] for n in record["tree"]["static"]["children"]
            if n.get("origin") == "universal"]


def test_full_run_writes_all_artifacts(tmp_path):
    # The merge copies a universal-looking leaf; code must replace it.
    stray = leaf("页面能打开", [], origin="universal")
    llm = FakeLLM({"spec": [spec()], "draft": [draft()], "merge": [_merged(extra_leaf=stray)],
                   "critic": [NO_ISSUES]})
    result, run_dir = _run(llm, tmp_path)

    assert result == {"valid": 1, "failed": 0}
    assert llm.stages() == ["spec", "draft", "draft", "draft", "merge", "critic"]
    assert [c["temperature"] for c in llm.calls if c["stage"] == "draft"] == [0.7] * 3
    case_dir = run_dir / "cases" / CASE["id"]
    for name in ("spec.json", "draft_1.json", "draft_2.json", "draft_3.json", "merged.json",
                 "critic_1.json", "final.json", "calls.jsonl"):
        assert (case_dir / name).exists(), name
    assert not (case_dir / "revised_1.json").exists()
    assert (run_dir / "config.json").exists()

    record = _final(run_dir)
    assert [json.loads(line) for line in (run_dir / "rubrics.jsonl").read_text().splitlines()] == [record]
    assert (run_dir / "failed.jsonl").read_text() == ""
    assert schema.validate(record) == []
    assert _universal(record) == ["页面正常加载，无白屏或阻断使用的报错", "界面主要文字使用中文"]
    assert "support" in (case_dir / "merged.json").read_text()
    assert "support" not in json.dumps(record["tree"])
    # mean of 3 equal draft proposals and the spec proposal (2, 1, 2, 3) / 8
    assert record["branch_weights"]["dynamic"] == pytest.approx((3 * 0.25 + 3 / 8) / 4)
    assert record["meta"]["usage"]["calls"] == 6
    assert record["meta"]["critic_rounds"] == 1
    assert record["meta"]["stats"]["leaves"] == 16
    assert len((case_dir / "calls.jsonl").read_text().splitlines()) == 6


def test_blocking_issue_triggers_revise_then_critic_again(tmp_path):
    revised = {"branch_weights": {"intention": 1, "content": 1, "static": 1, "dynamic": 5},
               "tree": tree()}
    llm = FakeLLM({"spec": [spec()], "draft": [draft()], "merge": [_merged()],
                   "critic": [BLOCKING, NO_ISSUES], "revise": [revised]})
    result, run_dir = _run(llm, tmp_path)

    assert result["valid"] == 1
    assert llm.stages()[-3:] == ["critic", "revise", "critic"]
    case_dir = run_dir / "cases" / CASE["id"]
    assert (case_dir / "revised_1.json").exists() and (case_dir / "critic_2.json").exists()
    record = _final(run_dir)
    assert record["meta"]["critic_rounds"] == 2
    assert record["branch_weights"]["dynamic"] == pytest.approx(5 / 8)


def test_critic_rounds_are_capped(tmp_path):
    llm = FakeLLM({"spec": [spec()], "draft": [draft()], "merge": [_merged()],
                   "critic": [BLOCKING], "revise": [{"tree": tree()}]})
    result, run_dir = _run(llm, tmp_path, critic_rounds=2)
    assert result["valid"] == 1
    assert llm.stages().count("critic") == 2 and llm.stages().count("revise") == 2
    assert not (run_dir / "cases" / CASE["id"] / "critic_3.json").exists()


def test_resume_skips_finished_cases(tmp_path):
    responses = {"spec": [spec()], "draft": [draft()], "merge": [_merged()], "critic": [NO_ISSUES]}
    llm = FakeLLM(responses)
    _run(llm, tmp_path)
    n_calls = len(llm.calls)
    result, _ = _run(llm, tmp_path)
    assert result["valid"] == 1 and len(llm.calls) == n_calls
    _run(llm, tmp_path, force=True)
    assert len(llm.calls) == 2 * n_calls


def test_invalid_case_goes_to_failed_jsonl(tmp_path):
    small = tree()
    small["static"]["children"] = small["static"]["children"][2:]   # 11 + 2 universal
    llm = FakeLLM({"spec": [spec()], "draft": [draft()], "merge": [{"tree": small}],
                   "critic": [NO_ISSUES], "repair_tree": [{"tree": small}]})
    result, run_dir = _run(llm, tmp_path)

    assert result == {"valid": 0, "failed": 1}
    assert llm.stages().count("repair_tree") == pipeline.MAX_REPAIRS
    assert (run_dir / "rubrics.jsonl").read_text() == ""
    failed = [json.loads(line) for line in (run_dir / "failed.jsonl").read_text().splitlines()]
    assert failed[0]["id"] == CASE["id"]
    assert any("tree has 13 leaves" in e for e in failed[0]["errors"])


def test_repair_fixes_a_validation_error(tmp_path):
    bad = tree()
    bad["static"]["children"][1]["weight"] = 9
    llm = FakeLLM({"spec": [spec()], "draft": [draft()], "merge": [{"tree": bad}],
                   "critic": [NO_ISSUES], "repair_tree": [{"tree": tree()}]})
    result, run_dir = _run(llm, tmp_path)
    assert result["valid"] == 1
    assert llm.stages().count("repair_tree") == 1
    repair_prompt = llm.calls[-1]["messages"][1]["content"]
    assert "S.2: weight must be an integer 1-5; got 9" in repair_prompt


def test_spec_is_repaired_before_drafting(tmp_path):
    bad = spec()
    bad["requirements"][0]["evidence_quote"] = "我没说过这句话"
    llm = FakeLLM({"spec": [bad], "repair_spec": [spec()], "draft": [draft()],
                   "merge": [_merged()], "critic": [NO_ISSUES]})
    result, run_dir = _run(llm, tmp_path)
    assert result["valid"] == 1
    assert llm.stages()[:3] == ["spec", "repair_spec", "draft"]
    assert _final(run_dir)["spec"] == spec()


def test_one_draft_skips_the_merge(tmp_path):
    llm = FakeLLM({"spec": [spec()], "draft": [draft()], "critic": [NO_ISSUES]})
    result, _ = _run(llm, tmp_path, drafts=1)
    assert result["valid"] == 1
    assert llm.stages() == ["spec", "draft", "critic"]


def test_one_draft_per_draft_model(tmp_path):
    llm = FakeLLM({"spec": [spec()], "draft": [draft()], "merge": [_merged()],
                   "critic": [NO_ISSUES]}, draft_models=["model-a", "model-b"], critic_model="judge")
    _run(llm, tmp_path)
    assert [c["model"] for c in llm.calls if c["stage"] == "draft"] == ["model-a", "model-b"]
    assert [c["model"] for c in llm.calls if c["stage"] == "critic"] == ["judge"]


def test_baseline_method(tmp_path):
    wdj = {"intention": {"description": "目的", "children": [{"description": "记录喝水", "children": None}]},
           "static": {"description": "元素", "children": [{"description": "饮水列表", "children": None}]},
           "dynamic": {"description": "交互", "children": [
               {"description": "基础", "children": [{"description": "点击加一杯", "children": None}]},
               {"description": "复杂", "children": [{"description": "刷新后仍在", "children": None}]}]}}
    llm = FakeLLM({"baseline": [wdj]})
    result, run_dir = _run(llm, tmp_path, method="webdevjudge_baseline")

    assert result["valid"] == 1 and llm.stages() == ["baseline"]
    record = _final(run_dir)
    assert record["method"] == "webdevjudge_baseline" and record["spec"] is None
    assert record["tree"]["content"]["children"] == []
    assert record["branch_weights"] == pytest.approx(
        {"intention": 1 / 6, "content": 0, "static": 0.5, "dynamic": 1 / 3})
    assert record["tree"]["dynamic"]["children"][1]["children"][0] == {
        "id": "D.C.1", "description": "刷新后仍在", "weight": 1, "critical": False,
        "origin": "explicit", "covers": [], "verify_by": "interaction", "children": None}
    assert to_webdevjudge(record)["rubric_tree"] == wdj


def test_baseline_with_bad_structure_is_repaired(tmp_path):
    good = {"intention": {"description": "目的", "children": [{"description": "a", "children": None}]},
            "static": {"description": "元素", "children": [{"description": "b", "children": None}]},
            "dynamic": {"description": "交互", "children": [{"description": "基础", "children": None},
                                                         {"description": "复杂", "children": None}]}}
    bad = {**good, "dynamic": {"description": "交互", "children": [{"description": "x", "children": None}]}}
    llm = FakeLLM({"baseline": [bad], "repair_baseline": [{"rubric_tree": good}]})
    result, _ = _run(llm, tmp_path, method="webdevjudge_baseline")
    assert result["valid"] == 1 and llm.stages() == ["baseline", "repair_baseline"]
