"""Test doubles: a FakeLLM with canned responses per stage, and canned objects."""
from __future__ import annotations

import json

from rubric_tree import archetypes, schema
from rubric_tree.llm import LLM

QUERY = "做一个记录每天喝水量的小应用，提醒我按时喝水，还要能看到一周的统计。"
CASE = {"id": "case-x", "prompt": QUERY}


class FakeLLM(LLM):
    """Raw responses per stage. A response is a str (sent as is) or an object
    (sent as JSON). Each call takes the next one; the last one repeats."""

    def __init__(self, responses: dict[str, list], **kwargs):
        super().__init__(model="fake-model", **kwargs)
        self.responses = {stage: list(items) for stage, items in responses.items()}
        self.calls: list[dict] = []

    async def _complete(self, messages, *, model, temperature, seed, stage):
        self.calls.append({"stage": stage, "model": model, "temperature": temperature,
                           "seed": seed, "messages": messages})
        queue = self.responses[stage]
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        return text, {"prompt_tokens": 100, "completion_tokens": 10}

    def stages(self) -> list[str]:
        return [c["stage"] for c in self.calls]


def spec() -> dict:
    return {
        "archetypes": ["tracker"],
        "delivery": "unspecified",
        "ui_language": "zh",
        "design_focus": False,
        "time_frame": {"date": "2026-10-12"},
        "requirements": [
            {"id": "R1", "type": "explicit", "text": "记录每天喝水量",
             "evidence_quote": "记录每天喝水量", "critical": True},
            {"id": "R2", "type": "explicit", "text": "提醒按时喝水",
             "evidence_quote": "提醒我按时喝水", "critical": False},
            {"id": "R3", "type": "explicit", "text": "看到一周的统计",
             "evidence_quote": "要能看到一周的统计", "critical": False},
            {"id": "R4", "type": "implicit", "text": "记录长期保存",
             "rationale": "每天都要用", "critical": True},
        ],
        "knowledge_needs": [{"topic": "成人每日建议饮水量", "generator_confident": True}],
    }


def leaf(text, covers=("R1",), *, origin="explicit", verify_by="view",
         critical=False) -> dict:
    return {"description": text, "critical": critical, "origin": origin,
            "covers": list(covers), "verify_by": verify_by, "children": None}


def group(text, children) -> dict:
    return {"description": text, "critical": False, "children": children}


def tree() -> dict:
    """A draft tree with 14 leaves. Code adds 3 universal leaves: 17 in total."""
    return {
        "intention": {"description": "目标", "children": [
            leaf("能记录喝水", ["R1"]), leaf("能提醒喝水", ["R2"]), leaf("能看一周统计", ["R3"])]},
        "content": {"description": "内容", "children": [
            leaf("建议饮水量合理", ["R1"], verify_by="fact"), leaf("统计数字与记录一致", ["R3"])]},
        "static": {"description": "页面", "children": [
            group("记录区", [leaf("显示今天已喝的量"), leaf("显示一周的图表", ["R3"])]),
            leaf("显示下次提醒时间", ["R2"]),
            leaf("无记录时提示先添加", [], origin="archetype")]},
        "dynamic": {"description": "交互", "children": [
            group("基础交互", [leaf(f"基础操作{i}", ["R1"], verify_by="interaction")
                           for i in range(1, 4)]),
            group("复杂交互", [
                leaf("刷新后记录仍在", ["R4"], origin="implicit", verify_by="interaction", critical=True),
                leaf("加一条记录后统计更新", ["R3"], verify_by="interaction")])]},
    }


def draft() -> dict:
    return {"tree": tree()}


def record() -> dict:
    """A valid full-method record, with ids, built from spec() and tree()."""
    s = spec()
    t = schema.normalize_tree(tree())
    t["static"]["children"] += archetypes.universal_leaves(s)
    schema.assign_ids(t)
    return {"id": CASE["id"], "prompt": QUERY, "as_of": "2026-10-12", "method": "full",
            "spec": s, "tree": t, "meta": {}}


def node(rec: dict, node_id: str) -> dict:
    for branch in schema.BRANCHES:
        for n, _ in schema.iter_nodes(rec["tree"][branch]):
            if n["id"] == node_id:
                return n
    raise KeyError(node_id)
