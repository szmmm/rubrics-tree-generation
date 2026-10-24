# rubrics-tree-generation

Input: web-app generation queries, one JSON object per line (`{"id", "prompt"}`, and optionally `"as_of": "YYYY-MM-DD"`, the date the user wrote the query).
Output: one rubric tree per query. A judge uses the tree to grade a generated app or to compare two apps.

The design is in [PLAN.md](PLAN.md). This is the Phase 1 implementation.

## Pipeline

```
query ─▶ [1 spec] ─▶ [2 archetype guidance] ─▶ [3 K drafts] ─▶ [4 merge] ─▶ [5 critic ⇄ revise] ─▶ [6 validate ⇄ repair] ─▶ tree
          (LLM)          (code)                   (LLM ×K)       (LLM)        (LLM, ≤ 2 rounds)        (code + LLM, ≤ 2 repairs)
```

The tree has four branches: `intention`, `content`, `static`, `dynamic` (`dynamic` has the groups basic `D.B` and complex `D.C`).
Each leaf is one yes/no check, with a `critical` flag, an `origin`, the spec requirements it `covers`, and a `verify_by` method.
Code assigns all ids, adds the universal leaves and runs the validator.
The reference scorer in `rubric_tree/score.py` defines what the gates mean. There are no node or branch weights: a node is critical or not. A failed critical node sets the whole score to 0 (decided 2026-10-20). Else the score is the pass rate over all leaves; the branches only group the leaves (decided 2026-10-23).

## Setup

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env    # then fill in RT_BASE_URL, RT_API_KEY, RT_MODEL
source .env
```

The system Python on this machine has no `venv`/`pip` module. Use `uv`.

## Run

```bash
# 5 cases first (PLAN Phase 1, step 6), both methods
.venv/bin/python -m rubric_tree generate --input genwebapp_v50.jsonl --run-name v1 \
    --ids case-06,case-13,case-15,case-16,case-18 --as-of 2026-10-09
.venv/bin/python -m rubric_tree generate --input genwebapp_v50.jsonl --run-name v1-baseline \
    --method webdevjudge_baseline --ids case-06,case-13,case-15,case-16,case-18

# review
.venv/bin/python -m rubric_tree stats  runs/v1/rubrics.jsonl
.venv/bin/python -m rubric_tree export runs/v1/rubrics.jsonl --format markdown --out runs/v1/review.md
.venv/bin/python -m rubric_tree export runs/v1/rubrics.jsonl --format webdevjudge --out runs/v1/wdj.jsonl
```

Options of `generate`:

| Option | Default | Meaning |
|---|---|---|
| `--method` | `full` | `full` or `webdevjudge_baseline` (one call, WebDevJudge structure) |
| `--as-of` | today | The user's today for cases without an `as_of` field. The spec stage keeps it, unless the query's own words show another time (`spec.time_frame`). Calendar words ("今年", "明年", "国庆节") are resolved against that date into absolute dates; freshness words ("最近", "最新") stay relative, and the judge checks them on the evaluation date. |
| `--drafts` | 3 | Number of drafts. `RT_DRAFT_MODELS` replaces it with one draft per model. |
| `--critic-rounds` | 1 | Maximum critic ⇄ revise rounds |
| `--env-profile` | `either` | What the app can use: `either` (not known: frontend only or full stack), `frontend_static` or `fullstack`. Leaf feasibility depends on it. |
| `--ids` | all | Comma-separated case ids |
| `--concurrency` | 8 | Maximum parallel LLM requests |
| `--force` | off | Generate every selected case again from an empty directory |

Every LLM call samples at temperature 1.0 and top_p 0.95, the sampling DeepSeek recommends for thinking. At temperature 0, DeepSeek-V4 often repeated the same lines in its thinking until the token cap (2026-10-24).
Every LLM call asks for thinking at `high` effort (`reasoning_effort` plus `chat_template_kwargs.thinking`, which DeepSeek-V4 on SGLang needs). Set `RT_REASONING_EFFORT` to `low`, `max` or `off` to change it. A 100-query DSV4-Flash run at `max` effort (2026-10-24) hit the token cap in 16% of draft calls with no answer yet, and those calls took 39% of all tokens; `high` is the default for that reason.
A call may produce at most 131072 tokens, reasoning included; set `RT_MAX_TOKENS` to change the cap. A response cut off at the cap counts as a failed attempt and is retried. Qwen3.8-27B runs with the old 65536 cap were cut off 4 times, so keep the server's `--context-length` above prompt plus cap (the DSV4 server on h20-2 has 384000).

Every stage output is saved when the stage ends (each draft on its own), and a saved stage is not run again.
A case that fails is retried in the same run, 2 more times, from its first missing stage. Only then does it go to `failed.json`.
A case with `final.json` is skipped on a rerun. A failed or unfinished case (for example after a crash) continues from its first missing stage.
A resumed case uses the saved stages as they are, so use a new `--run-name` when you change options, or `--force`.
For a big input, run batches of a few hundred ids (`--ids`) into one `--run-name`; `rubrics.jsonl` then holds every batch so far.
The `usage` in a record counts only the calls of the run that finished the case; `calls.jsonl` has all of them.

## Outputs

```
runs/<run_name>/
  config.json
  rubrics.jsonl          # one valid record per line, in input order
  failed.jsonl           # cases that stayed invalid after 2 repairs, with the errors
  cases/<case_id>/
    spec.json  draft_1.json … draft_K.json  merged.json
    critic_1.json  revised_1.json  critic_2.json …
    final.json | failed.json
    calls.jsonl          # every LLM attempt: prompt, response, model, temperature, reasoning effort, usage, latency
```

`rubrics.jsonl` and `failed.jsonl` are rebuilt from the case directories at the end of every run.

## Layout

```
rubric_tree/
  schema.py      tree helpers, id assignment, validate_spec, validate, webdevjudge_errors
  archetypes.py  archetype guidance and the universal leaves
  prompts.py     every stage prompt and the hand-written worked example
  llm.py         OpenAI-compatible client: JSON extraction, parse retries, calls.jsonl
  pipeline.py    the stages, run_case, run_all
  score.py       reference scorer
  export.py      WebDevJudge format and Markdown
  stats.py       leaves, depth, origin and verify_by mix
tests/           offline tests; FakeLLM returns canned responses per stage
```

## Tests

```bash
.venv/bin/python -m pytest
```

The tests use no network. They cover each validator rule, the scorer gates, JSON retries, resume, failure handling, repair, the baseline, the exports and the CLI.
One test checks that the worked example in `prompts.py` passes the validator.

## Differences from PLAN.md

- Records and nodes are plain dicts in the JSON shape, not dataclasses.
- At most 5 critical leaves besides the universal leaves (decided 2026-10-24). In a 100-query run the critic asked for a 5th critical leaf of the LLM's own in about half of the trees, and the universal one made it 6. At the cap, the critic asks to swap a critical flag, not to add one.
- A draft, merge, revise or tree repair that does not return the four branches is retried like a response without JSON. Revise once returned only the branch it changed (8 of 100 cases).
- Every call samples at temperature 1.0 and top_p 0.95. PLAN's draft temperature 0.7 and the 0.1 rise per JSON retry are not used; a retry gets a new seed.
- Code removes and adds the universal leaves again after every LLM rewrite (merge, revise, repair). Thus no LLM can change them.
- Stage 1 validates and repairs the spec before the drafts start. A tree repair cannot fix a bad spec.
- The `evidence_quote` check ignores whitespace differences.
- `content` can be empty only when `spec.knowledge_needs` is empty. ("No requirement mentions content" is not a check that code can do.)
- With `--drafts 1`, there is no merge call.
- Environment profiles `either` (default), `frontend_static` and `fullstack` are available.
- The baseline prompt is our own text. Its example is the worked example, converted to the WebDevJudge format, because the WebDevJudge repository has no license.
- The baseline also gets the repair loop, with the WebDevJudge structure check.

## Status

- Phase 1 steps 1, 2, 4 and 5: done and tested offline.
- Step 3 (review of `archetypes.py` and `prompts.py`): open for the user.
- Steps 6 and 7 (real runs): not done. No LLM endpoint is set up for this project.
