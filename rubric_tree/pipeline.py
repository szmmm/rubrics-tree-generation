"""The generation pipeline (PLAN §4).

query → spec → archetype guidance → K drafts → merge → critic ⇄ revise
      → validate ⇄ repair → tree

Every stage output goes to runs/<run>/cases/<id>/. A case with final.json is
skipped on a rerun unless force is set. Any other case starts again from an
empty directory. rubrics.jsonl and failed.jsonl are rebuilt from the case
directories at the end of every run, in input order.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import shutil
import traceback
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from . import archetypes, export, prompts, schema, stats
from .llm import LLM

logger = logging.getLogger(__name__)

METHODS = ("full", "webdevjudge_baseline")
MAX_REPAIRS = 2
DRAFT_TEMPERATURE = 0.7
BASELINE_WEIGHTS = {"intention": 1, "content": 0, "static": 3, "dynamic": 2}   # WebDevJudge


@dataclass
class Options:
    method: str = "full"
    as_of: str = field(default_factory=lambda: date.today().isoformat())
    drafts: int = 3
    critic_rounds: int = 1
    env_profile: str = "either"
    force: bool = False


class CaseFailed(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class _Case:
    """One query's run: its directory, its LLM calls and their usage."""

    def __init__(self, llm: LLM, case: dict, case_dir: Path, opts: Options):
        self.llm, self.opts, self.dir = llm, opts, case_dir
        self.id, self.query = case["id"], case["prompt"]
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}

    async def call(self, stage: str, messages: list[dict], *, model: str = "",
                   temperature: float = 0.0) -> dict:
        obj, usage = await self.llm.chat_json(messages, stage=stage, model=model,
                                              temperature=temperature,
                                              log_path=self.dir / "calls.jsonl")
        for key in self.usage:
            self.usage[key] += usage[key]
        return obj

    def save(self, name: str, obj) -> None:
        _write_json(self.dir / name, obj)


async def run_all(llm: LLM, cases: list[dict], run_dir: Path, opts: Options,
                  ids: set[str] | None = None) -> dict:
    """Run the selected cases (all when ids is None), then rebuild the outputs."""
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "config.json", {**asdict(opts), "models": _models(llm, opts)})
    selected = [c for c in cases if ids is None or c["id"] in ids]
    await asyncio.gather(*(run_case(llm, c, run_dir, opts) for c in selected))
    return _rebuild(cases, run_dir)


async def run_case(llm: LLM, case: dict, run_dir: Path, opts: Options) -> dict | None:
    """The final record, or None if the case failed (see its failed.json)."""
    case_dir = run_dir / "cases" / case["id"]
    final = case_dir / "final.json"
    if final.exists() and not opts.force:
        logger.info("%s: already done, skipped", case["id"])
        return json.loads(final.read_text(encoding="utf-8"))
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)

    c = _Case(llm, case, case_dir, opts)
    logger.info("%s: start (%s)", c.id, opts.method)
    try:
        record = await (_run_full(c) if opts.method == "full" else _run_baseline(c))
    except Exception as e:  # noqa: BLE001 - one case must not stop the others
        failure = {"id": c.id, "prompt": c.query, "method": opts.method,
                   "errors": e.errors if isinstance(e, CaseFailed)
                   else [f"{type(e).__name__}: {e}"]}
        if not isinstance(e, CaseFailed):
            failure["traceback"] = traceback.format_exc()
        c.save("failed.json", failure)
        logger.warning("%s: failed: %s", c.id, "; ".join(failure["errors"])[:500])
        return None
    c.save("final.json", record)
    logger.info("%s: done, %d leaves, %d calls", c.id, record["meta"]["stats"]["leaves"],
                c.usage["calls"])
    return record


async def _run_full(c: _Case) -> dict:
    opts = c.opts
    spec = await _spec(c)
    universal = archetypes.universal_leaves(spec)

    # Stage 2 (code) and stage 3: K independent drafts.
    guidance = archetypes.guidance(spec["archetypes"])
    models = c.llm.draft_models or [c.llm.model] * opts.drafts
    draft_msgs = prompts.draft_messages(c.query, opts.as_of, opts.env_profile, spec,
                                        guidance, universal)
    drafts = await asyncio.gather(*(
        c.call("draft", draft_msgs, model=m, temperature=DRAFT_TEMPERATURE) for m in models))
    for i, draft in enumerate(drafts, 1):
        c.save(f"draft_{i}.json", draft)

    # Stage 4: merge, then the code steps.
    # Only the four branches go to the merge: never the draft's weights.
    trees = [{b: t[b] for b in schema.BRANCHES if b in t}
             for t in (d.get("tree", d) for d in drafts)]
    if len(trees) == 1:
        tree = trees[0]
    else:
        out = await c.call("merge", prompts.merge_messages(
            c.query, opts.as_of, opts.env_profile, spec, trees, universal))
        tree = out.get("tree", out)
    weights = _mean_weights([d.get("branch_weight_proposal") for d in drafts])
    tree = _prepare(tree, universal)
    c.save("merged.json", {"branch_weights": weights, "tree": tree})

    # Stage 5: critic ⇄ revise.
    rounds = 0
    for r in range(1, opts.critic_rounds + 1):
        out = await c.call("critic", prompts.critic_messages(
            c.query, opts.as_of, opts.env_profile, spec, tree),
            model=c.llm.critic_model)
        issues = out.get("issues") if isinstance(out.get("issues"), list) else []
        c.save(f"critic_{r}.json", issues)
        rounds = r
        if not any(isinstance(i, dict) for i in issues):
            break
        out = await c.call("revise", prompts.revise_messages(
            c.query, opts.as_of, opts.env_profile, spec, tree, issues))
        tree = _prepare(out.get("tree", out), universal)
        c.save(f"revised_{r}.json", {"tree": tree})

    # Stage 6: validate ⇄ repair.
    def prepare(obj: dict) -> dict:
        return {"tree": _prepare(obj.get("tree", obj), universal)}

    def errors_of(obj: dict) -> list[str]:
        return schema.validate(_record(c, spec, weights, obj["tree"]))

    obj = await _until_valid(c, {"tree": tree}, kind="tree",
                             errors_of=errors_of, prepare=prepare, spec=spec)
    return _finish(c, spec, weights, _strip_support(obj["tree"]), {
        "models": _models(c.llm, opts), "n_drafts": len(drafts), "critic_rounds": rounds})


async def _spec(c: _Case) -> dict:
    """Stage 1: query analysis, repaired until it passes validate_spec."""
    spec = await c.call("spec", prompts.spec_messages(c.query, c.opts.as_of, c.opts.env_profile))
    spec = await _until_valid(c, spec, kind="spec", prepare=lambda s: s,
                              errors_of=lambda s: schema.validate_spec(s, c.query))
    c.save("spec.json", spec)
    return spec


async def _run_baseline(c: _Case) -> dict:
    """One WebDevJudge-style call, converted to our schema (PLAN §4.8)."""
    out = await c.call("baseline", prompts.baseline_messages(c.query))
    wdj = await _until_valid(c, out.get("rubric_tree", out), kind="baseline",
                             prepare=lambda o: o.get("rubric_tree", o),
                             errors_of=schema.webdevjudge_errors)
    tree = schema.assign_ids(export.from_webdevjudge(wdj))
    return _finish(c, None, _normalize_weights(BASELINE_WEIGHTS), tree,
                   {"models": {"default": c.llm.model}})


async def _until_valid(c: _Case, obj, *, kind: str, errors_of, prepare,
                       spec: dict | None = None):
    """Ask the LLM to fix the validator errors, at most MAX_REPAIRS times."""
    errors = errors_of(obj)
    for _ in range(MAX_REPAIRS):
        if not errors:
            break
        fixed = await c.call(f"repair_{kind}", prompts.repair_messages(
            obj, errors, query=c.query, kind=kind, spec=spec))
        obj = prepare(fixed)
        errors = errors_of(obj)
    if errors:
        raise CaseFailed(errors)
    return obj


def _prepare(tree, universal: list[dict]):
    """Normalize an LLM-written tree, put the universal leaves in, assign ids."""
    tree = schema.normalize_tree(tree)
    if isinstance(tree, dict):
        for node in tree.values():
            _drop_universal(node)
        static = tree.get("static")
        if isinstance(static, dict):
            if not isinstance(static.get("children"), list):
                static["children"] = []
            static["children"] += copy.deepcopy(universal)
        schema.assign_ids(tree)
    return tree


def _drop_universal(node) -> None:
    """Remove universal leaves, so code alone decides what they say."""
    if isinstance(node, dict) and isinstance(node.get("children"), list):
        node["children"] = [c for c in node["children"]
                            if not (isinstance(c, dict) and c.get("origin") == "universal")]
        for child in node["children"]:
            _drop_universal(child)


def _strip_support(tree: dict) -> dict:
    for branch in schema.BRANCHES:
        for node, _ in schema.iter_nodes(tree[branch]):
            node.pop("support", None)
    return tree


def _normalize_weights(weights) -> dict | None:
    """Weights scaled to sum 1, or None if they are not four numbers >= 0."""
    if not isinstance(weights, dict):
        return None
    try:
        values = {b: float(weights[b]) for b in schema.BRANCHES}
    except (KeyError, TypeError, ValueError):
        return None
    total = sum(values.values())
    if total <= 0 or min(values.values()) < 0:
        return None
    return {b: v / total for b, v in values.items()}


def _mean_weights(proposals: list) -> dict:
    """Mean of the valid draft proposals, each scaled to sum 1 first (RACE).
    Equal weights if no proposal is valid."""
    valid = [w for p in proposals if (w := _normalize_weights(p))]
    if not valid:
        return {b: 1 / len(schema.BRANCHES) for b in schema.BRANCHES}
    return {b: sum(w[b] for w in valid) / len(valid) for b in schema.BRANCHES}


def _record(c: _Case, spec: dict | None, weights: dict, tree: dict,
            meta: dict | None = None) -> dict:
    return {"id": c.id, "prompt": c.query, "as_of": c.opts.as_of, "method": c.opts.method,
            "spec": spec, "branch_weights": weights, "tree": tree, "meta": meta or {}}


def _finish(c: _Case, spec: dict | None, weights: dict, tree: dict, meta: dict) -> dict:
    record = _record(c, spec, weights, tree, {
        **meta, "env_profile": c.opts.env_profile, "usage": dict(c.usage)})
    record["meta"]["stats"] = stats.tree_stats(record)
    return record


def _models(llm: LLM, opts: Options) -> dict:
    return {"default": llm.model,
            "drafts": llm.draft_models or [llm.model] * opts.drafts,
            "critic": llm.critic_model}


def _rebuild(cases: list[dict], run_dir: Path) -> dict:
    finals, failures = [], []
    for case in cases:
        case_dir = run_dir / "cases" / case["id"]
        if (case_dir / "final.json").exists():
            finals.append(json.loads((case_dir / "final.json").read_text(encoding="utf-8")))
        elif (case_dir / "failed.json").exists():
            failures.append(json.loads((case_dir / "failed.json").read_text(encoding="utf-8")))
    for name, rows in (("rubrics.jsonl", finals), ("failed.jsonl", failures)):
        (run_dir / name).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return {"valid": len(finals), "failed": len(failures)}


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
