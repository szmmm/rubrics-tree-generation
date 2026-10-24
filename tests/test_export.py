import json

import pytest

from fakes import record
from rubric_tree import export, prompts, schema
from rubric_tree.__main__ import main


def test_to_webdevjudge_passes_the_webdevjudge_structure_check():
    rec = record()
    line = export.to_webdevjudge(rec)
    assert line["question_id"] == rec["id"]
    wdj = line["rubric_tree"]
    assert schema.webdevjudge_errors(wdj) == []
    # content goes into static as its last group
    assert wdj["static"]["children"][-1]["description"] == rec["tree"]["content"]["description"]
    n_leaves = json.dumps(wdj, ensure_ascii=False).count('"children": null')
    assert n_leaves == sum(len(schema.leaves(rec["tree"][b])) for b in schema.BRANCHES)


def test_baseline_prompt_example_is_a_valid_webdevjudge_tree():
    assert schema.webdevjudge_errors(export.webdevjudge_tree(prompts.EXAMPLE_TREE)) == []


def test_markdown_shows_ids_tags_and_spec():
    text = export.to_markdown([record()])
    assert "## case-x · full" in text
    assert "`D.C.1` [**critical** · implicit R4 · interaction] 刷新后记录仍在" in text
    assert "- R4 (implicit, critical) 记录长期保存 — because: 每天都要用" in text


def test_cli_stats_and_export(tmp_path, capsys):
    rubrics = tmp_path / "rubrics.jsonl"
    rubrics.write_text(json.dumps(record(), ensure_ascii=False) + "\n", encoding="utf-8")

    assert main(["stats", str(rubrics)]) == 0
    table = capsys.readouterr().out
    assert "| case-x | full | 17 | 3 | 2 | 7 | 5 |" in table

    out = tmp_path / "wdj.jsonl"
    assert main(["export", str(rubrics), "--format", "webdevjudge", "--out", str(out)]) == 0
    assert schema.webdevjudge_errors(json.loads(out.read_text())["rubric_tree"]) == []

    md = tmp_path / "review.md"
    assert main(["export", str(rubrics), "--format", "markdown", "--out", str(md)]) == 0
    assert "case-x" in md.read_text(encoding="utf-8")


def test_markdown_shows_the_user_date():
    assert "user's today: 2026-10-12" in export.to_markdown([record()])
    rec = record()
    rec["spec"]["time_frame"] = {"date": "2025", "evidence_quote": "每天喝水量", "rationale": "测试",
                                 "refers_to": "2026年夏天"}
    text = export.to_markdown([rec])
    assert "user's today: 2025 · about: 2026年夏天" in text
    assert "- time: not as_of 2026-10-12 — “每天喝水量”, because: 测试" in text


def test_cli_rejects_a_bad_as_of(tmp_path):
    cases = tmp_path / "in.jsonl"
    cases.write_text(json.dumps({"id": "a", "prompt": "q", "as_of": "明年"}) + "\n",
                     encoding="utf-8")
    with pytest.raises(SystemExit, match="as_of is not a YYYY-MM-DD date: a"):
        main(["generate", "--input", str(cases), "--run-name", "x"])
