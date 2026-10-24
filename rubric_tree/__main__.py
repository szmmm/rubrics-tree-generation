"""Command line: generate, stats, export. See README.md."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import date
from pathlib import Path

from . import export, pipeline, prompts, stats
from .llm import LLM


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rubric_tree")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="generate rubric trees into runs/<run-name>/")
    gen.add_argument("--input", type=Path, required=True,
                     help="JSONL with id, prompt and an optional as_of")
    gen.add_argument("--run-name", required=True)
    gen.add_argument("--method", choices=pipeline.METHODS, default="full")
    gen.add_argument("--as-of", default=date.today().isoformat(),
                     help="the user's today for cases without an as_of field (default: today)")
    gen.add_argument("--drafts", type=int, default=3,
                     help="number of drafts; ignored when RT_DRAFT_MODELS is set")
    gen.add_argument("--critic-rounds", type=int, default=1)
    gen.add_argument("--env-profile", choices=sorted(prompts.ENV_PROFILES),
                     default="either")
    gen.add_argument("--ids", help="comma-separated case ids (default: all)")
    gen.add_argument("--concurrency", type=int, default=32, help="max parallel LLM requests")
    gen.add_argument("--force", action="store_true", help="regenerate finished cases")

    st = sub.add_parser("stats", help="print tree statistics as a Markdown table")
    st.add_argument("rubrics", type=Path)

    ex = sub.add_parser("export", help="convert rubrics.jsonl for review or for WebDevJudge")
    ex.add_argument("rubrics", type=Path)
    ex.add_argument("--format", choices=("markdown", "webdevjudge"), required=True)
    ex.add_argument("--out", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "generate":
        return _generate(args)
    records = _read_jsonl(args.rubrics)
    if args.command == "stats":
        print(stats.summary_table(records))
    elif args.format == "markdown":
        args.out.write_text(export.to_markdown(records), encoding="utf-8")
    else:
        args.out.write_text("".join(json.dumps(export.to_webdevjudge(r), ensure_ascii=False) + "\n"
                                    for r in records), encoding="utf-8")
    return 0


def _generate(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cases = _read_jsonl(args.input)
    bad = [c["id"] for c in cases if not _is_date(c.get("as_of", args.as_of))]
    if bad:
        raise SystemExit(f"as_of is not a YYYY-MM-DD date: {', '.join(bad)}")
    ids = None
    if args.ids:
        ids = {i.strip() for i in args.ids.split(",") if i.strip()}
        unknown = ids - {c["id"] for c in cases}
        if unknown:
            raise SystemExit(f"unknown ids: {', '.join(sorted(unknown))}")
    llm = LLM.from_env(concurrency=args.concurrency)
    opts = pipeline.Options(method=args.method, as_of=args.as_of, drafts=args.drafts,
                            critic_rounds=args.critic_rounds, env_profile=args.env_profile,
                            force=args.force)
    run_dir = Path("runs") / args.run_name
    result = asyncio.run(pipeline.run_all(llm, cases, run_dir, opts, ids))
    print(f"{run_dir}: {result['valid']} valid, {result['failed']} failed "
          f"(rubrics.jsonl, failed.jsonl)")
    return 0 if result["failed"] == 0 else 1


def _is_date(text) -> bool:
    try:
        return date.fromisoformat(text).isoformat() == text
    except (TypeError, ValueError):
        return False


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
