# Rubric-tree generation for web-app queries: design and implementation plan

Status: draft for review. Do not implement until the open questions in §9 have answers or the defaults are accepted.
Date: 2026-10-09.

## 0. Goal

Input: one web-app generation query (one line of `genwebapp_v50.jsonl`: `{"id", "prompt"}`).
Output: one **rubric tree** for that query. A judge (LLM, agent or human) uses the tree to grade a generated app, or to compare two apps.

The pipeline makes the tree. The judge is out of scope. The plan includes a small reference scorer only so that the tree semantics (weights, gates) are defined and testable.

Success criteria for the pipeline:

1. Every tree passes the deterministic validator (§4.6).
2. Every explicit requirement in the query is covered by at least one leaf.
3. Each leaf is atomic, binary, and checkable by a person with the running app in about 2 minutes.
4. Leaves do not demand one literal implementation when other implementations satisfy the user equally (functional equivalence).
5. Trees for the same query are stable across reruns (measured in Phase 2).
6. A rubric-based judge that uses our trees agrees with human preference more often than the same judge with WebDevJudge-baseline trees (measured in Phase 2, only if human labels exist).

## 1. What the input data shows

The 26 queries are in Chinese. They are short and under-specified. They differ in type:

| Type (archetype) | Cases | What matters most |
|---|---|---|
| Game / clone of a known game | 01, 15 | Rules are correct; win/lose state; restart; save/load (15) |
| Long-term tracker / habit app | 03, 04, 17, 19, 20, 21, 22, 23, 26 | Data persists after reload; create/edit/delete; statistics; a plan that advances by day or week |
| Guide / itinerary / advice page | 02, 05, 09, 11, 24, 25 | Content is correct, specific, consistent (budget sums), and fits the user's constraints |
| Showcase / fan / media page | 07, 12, 14, 18 | Real facts about a real person or event; images load; no invented content shown as fact |
| News / fresh information | 08, 16, 18 | Information is recent relative to a date; links are real |
| Decision / recommendation tool | 09, 13 | The logic uses the inputs; the output changes when the inputs change |
| Ambient / media player | 10, 26 | Audio plays and stops; mood and visual style match the request |

Three properties of this data drive the design:

- **Implicit requirements from personal context.** Examples: "高血糖父母" means low-sugar dishes with low glycemic index. "小孩两岁半" means child-friendly travel. "长期用" means persistence. The WebDevJudge prompt extracts only what the query states. We must also extract what it implies.
- **Content quality is often the main value.** For a travel guide, correct and useful information matters more than buttons. WebDevJudge puts content under `static`, mixed with "element is present". We give content its own branch.
- **Freshness and real-world facts.** "近期在映热门电影", "最近3年", "国庆节", "今年". The correct content depends on a date. The rubric generator may not know the facts. It must not write facts it is not sure of into leaves.

## 2. Related work and what we borrow

| Work | Institution | Idea we take | Where in pipeline |
|---|---|---|---|
| **WebDevJudge** (ICLR 2026, [arXiv 2510.18560](https://arxiv.org/abs/2510.18560), [code](https://github.com/lcy2723/WebDevJudge)) | Tencent AI Lab, HKUST, NTU | Query-grounded rubric tree with `intention` / `static` / `dynamic(basic, complex)`; binary atomic leaves; branch weights 1/3/2; the "functional equivalence" guideline; generated rubrics are "too specific or too broad" on vague queries; judge failure modes (literal reading, feasibility, position bias); pairwise > single grading | Base schema (§3); baseline method (§4.8); critic checks (§4.5) |
| **MiniAppBench / MiniAppEval** (ICML 2026, [arXiv 2603.09652](https://arxiv.org/abs/2603.09652)) | Inclusion AI (Ant Group), SJTU, CMU | Same three dimensions on real assistant queries; expert-written **domain-specific guidelines** given to the generating LLM; the reference is "a flexible inspection guide rather than a rigid template"; removing the reference cuts judge recall from 85% to 46% | Archetype guidance (§4.2) |
| **RubricsTree** ([arXiv 2606.18203](https://arxiv.org/abs/2606.18203)) | Google et al. | Fixed taxonomy of atomic Boolean rubrics plus a router that activates only the relevant ones per query | Archetype routing (§4.1, §4.2) |
| **PaperBench** ([arXiv 2504.01848](https://arxiv.org/abs/2504.01848)) | OpenAI | Weighted tree; weight is importance **relative to siblings**; decompose until an expert can check a leaf quickly; parent score = weighted mean of children | Node weights; leaf size rule; scorer (§3, §5) |
| **Mind2Web 2** ([arXiv 2506.21506](https://arxiv.org/abs/2506.21506)) | OSU | **Critical** nodes gate the parent ("gate-then-average"); non-critical nodes give partial credit | `critical` flag; scorer (§3, §5) |
| **RCCA** ([arXiv 2608.27906](https://arxiv.org/abs/2608.27906)) | Inclusion AI (Ant Group) | Web-app rubrics split into **initial-state** vs **after-interaction**; importance levels; score ceiling when an essential rubric fails; format/source/runtime gates before rubric checks | `verify_by` field; universal leaves (§4.4) |
| **Rubrics as Rewards (RaR)** ([arXiv 2507.17746](https://arxiv.org/abs/2507.17746)) | Scale AI | Desiderata: expert grounding, coverage, importance weights, **self-contained** items; Essential/Important/Optional/Pitfall; 7–20 items; pitfalls phrased positively; reference material improves rubrics; stronger generators make better rubrics | Leaf rules; weights; all leaves positive |
| **OpenRubrics / CRG** ([arXiv 2510.07743](https://arxiv.org/abs/2510.07743)) | Emory et al. | Split **hard rules** (explicit) from **principles** (implicit); contrastive generation from good vs bad responses; keep rubrics that predict the human preference label | `origin` field (§3); Phase 3 contrastive stage |
| **RLCF, "Checklists are better than reward models"** ([arXiv 2507.18624](https://arxiv.org/abs/2507.18624)) | CMU, Apple | Candidate-based checklists (from real failure modes) are more objective, atomic and complete than direct prompting; fixed **universal** items added to every checklist | Universal leaves (§4.4); Phase 3 |
| **DeepResearch Bench / RACE** ([arXiv 2506.11763](https://arxiv.org/abs/2506.11763)) | USTC et al. | Fixed top-level dimensions, **task-adaptive dimension weights**, averaged over several LLM trials | Branch weights averaged over drafts (§4.3) |
| **WebCoderBench** ([arXiv 2601.02430](https://arxiv.org/abs/2601.02430)) | PKU | Separate functional / visual / **content** alignment; checklists drafted by **3 different LLMs**, then merged | `content` branch; multi-draft merge (§4.3, §4.4) |
| **ARGO** ([OpenAI alignment blog](https://alignment.openai.com/argo/)) | OpenAI | Frontend reward models over-weight layout and typography; one page with broken buttons was preferred for its layout | Critic check: function must outweigh looks (§4.5) |
| **Agent-as-a-Judge / DevAI** ([arXiv 2410.10934](https://arxiv.org/abs/2410.10934)) | Meta, KAUST | Requirements vs softer preferences; dependencies between requirements | Considered; dependencies deferred (§10) |
| **HealthBench** ([arXiv 2505.08775](https://arxiv.org/abs/2505.08775)) | OpenAI | Per-conversation rubrics; axis tags such as accuracy, completeness, context awareness | `content` sub-structure; implicit-context leaves |
| **Interventional transfer** ([arXiv 2610.10809](https://arxiv.org/abs/2610.10809)) | — | Validate a rubric with perturbations: a rubric that catches defects may still fail to reward improvements; test both directions | Phase 2 perturbation test (§7) |

Summary of the design position: keep the WebDevJudge tree as the base, because WebDevJudge and MiniAppBench both validated it against humans. Add four things the data needs: (1) a query-analysis stage for explicit and implicit requirements, (2) archetype guidance, (3) a content branch with freshness rules, (4) multi-draft merge plus a critic loop for coverage and over-specificity.

## 3. Output schema

One JSON object per query. Output file: `rubrics.jsonl`, one line per case.

```jsonc
{
  "id": "case-06",
  "prompt": "我想做一份适合高血糖父母的家常菜谱……",
  "as_of": "2026-10-09",
  "method": "full",                       // "full" | "webdevjudge_baseline"
  "spec": { ... },                        // output of stage 1, see §4.1
  "branch_weights": {"intention": 0.20, "content": 0.30, "static": 0.15, "dynamic": 0.35},  // sum = 1
  "tree": {
    "intention": Node,
    "content":   Node,
    "static":    Node,
    "dynamic":   Node                     // exactly two children: id "D.B" (basic) and "D.C" (complex)
  },
  "meta": {"models": {...}, "n_drafts": 3, "critic_rounds": 1, "usage": {...}, "stats": {...}}
}
```

`Node`:

| Field | Type | Rule |
|---|---|---|
| `id` | str | Assigned by code, never by the LLM. Path form: `I`, `I.1`, `C.2.3`, `D.B.1`, `D.C.4`. |
| `description` | str | Internal node: short group name. Leaf: one yes/no statement, in the query language (see §9 Q3). |
| `weight` | int 1–5 | Importance relative to siblings (PaperBench). 5 = core, 3 = important, 1 = nice to have (RaR mapping). |
| `critical` | bool | If true and this node fails, its parent scores 0 (Mind2Web 2). Default false. |
| `children` | list[Node] \| null | null for a leaf. |
| Leaf only: `origin` | enum | `explicit` (stated in query) \| `implicit` (inferred from query context) \| `archetype` (default expectation for the app type) \| `universal` (fixed, added by code). |
| Leaf only: `covers` | list[str] | Spec requirement ids (`R1`, `R2` …) that this leaf checks. Required for `explicit` and `implicit`. |
| Leaf only: `verify_by` | enum | `view` (visible on load or in code) \| `interaction` (needs user actions; RCCA "dynamic") \| `fact` (needs external knowledge or search to check). |
| Leaf only: `note` | str, optional | Guidance for the judge: tolerance, accepted alternatives. Example: "任何清晰标注血糖友好的方式都可以，如标签、图标或分类". |

Branch meaning:

- `intention` (3–6 leaves): the core goals. "Does this app do what the user wanted at all?"
- `content` (0–15 leaves): the information the app shows. Accuracy, completeness, fit to the user's context, internal consistency (sums, dates), freshness. Empty only if the spec says the query has no content needs (for example a pure chess game).
- `static` (4–12 leaves): visible structure and look on load. Required sections and elements, readable layout, mobile layout when the user said "APP", visual style when the user asked for one.
- `dynamic.basic`: single-step interactions (tap, type, select, play).
- `dynamic.complex`: multi-step flows and state changes (create → reload → still there; finish a game; switch person and see other data).

Size target: 15–40 leaves in total, depending on query complexity. Max depth 4 below a branch root. WebDevJudge averaged 29.9 leaves and height 5.

### Worked example (fragment, case-06)

```jsonc
"content": {"id": "C", "description": "菜谱内容", "weight": 3, "critical": false, "children": [
  {"id": "C.1", "description": "每道菜都适合高血糖人群：主料避免高糖、精制主食为主的做法，或给出替换建议",
   "weight": 5, "critical": true, "origin": "implicit", "covers": ["R2"], "verify_by": "fact", "children": null},
  {"id": "C.2", "description": "菜品使用普通菜市场或超市容易买到的食材", "weight": 3, "critical": false,
   "origin": "explicit", "covers": ["R3"], "verify_by": "view", "children": null},
  {"id": "C.3", "description": "每道菜有分步骤的做法说明", "weight": 4, "critical": false,
   "origin": "explicit", "covers": ["R4"], "verify_by": "view", "children": null}
]},
"dynamic": {"id": "D", "children": [
  {"id": "D.B", "description": "基础交互", "children": [
    {"id": "D.B.1", "description": "用户可以浏览菜品并选中一道菜查看详情", "weight": 4, "origin": "explicit", "covers": ["R5"], "verify_by": "interaction", ...}]},
  {"id": "D.C", "description": "复杂交互", "children": [
    {"id": "D.C.1", "description": "用户把菜品加入家庭菜单后刷新页面，菜单仍然保留", "weight": 5, "critical": true,
     "origin": "implicit", "covers": ["R6"], "verify_by": "interaction",
     "note": "用户说要“长期当爸妈的家庭菜单”，需要持久化；localStorage 或后端都可以"}]}
]}
```

## 4. Pipeline

```
query ─▶ [1 Spec] ─▶ [2 Archetype guidance] ─▶ [3 K drafts] ─▶ [4 Merge] ─▶ [5 Critic ⇄ Revise] ─▶ [6 Validate ⇄ Repair] ─▶ tree
              (LLM)        (code lookup)          (LLM ×K)       (LLM)          (LLM, ≤2 rounds)         (code + LLM)
```

LLM calls per query with defaults: 1 + 3 + 1 + up to 4 + up to 2 ≈ 9–11. For 26 queries this is about 250 calls.

### 4.1 Stage 1: query analysis → `spec` (one LLM call)

Inputs: query, `as_of` date, environment profile (§9 Q2).
Output (JSON):

```jsonc
{
  "archetypes": ["tracker", "guide"],          // 1–3 ids from the fixed list in archetypes.py
  "delivery": "mobile_app" | "single_page" | "unspecified",
  "ui_language": "zh",
  "design_focus": false,                       // true only if the query asks for a look or mood (case-10 "竹林幽静氛围")
  "requirements": [
    {"id": "R1", "type": "explicit", "text": "推荐书籍", "evidence_quote": "要能推荐书籍", "importance": 5},
    {"id": "R2", "type": "implicit", "text": "推荐的书与教育孩子和管理相关", "rationale": "用户说想看启迪教育小孩、做好管理者的书", "importance": 5},
    {"id": "R3", "type": "implicit", "text": "进度支持一年 24 本的目标", "rationale": "今年读完 24 本书", "importance": 4}
  ],
  "knowledge_needs": [                         // facts the app must show and a judge must check
    {"topic": "国庆期间海南亲子景点与天气", "freshness": "seasonal" | "recent" | "stable", "generator_confident": false}
  ],
  "ambiguities": ["未说明是否需要多用户", "…"],
  "branch_weight_proposal": {"intention": 2, "content": 3, "static": 1, "dynamic": 3},
  "branch_weight_reason": "…"
}
```

Rules in the prompt:

- Explicit requirement = stated in the query. `evidence_quote` must be an exact substring of the query (code checks this).
- Implicit requirement = a need that a reasonable user with this context would expect, with a `rationale` that cites the context. Do not add features the user did not hint at. (OpenRubrics "principles"; HealthBench "context awareness".)
- Resolve relative dates against `as_of` ("今年" = 2026, "国庆节" = 2026-10-01 to 10-07, "最近3年" = 2023-10 to 2026-10).
- Mark `generator_confident: false` for facts the model cannot state with confidence at `as_of`.
- List ambiguities. Later stages must accept any reasonable reading of an ambiguity.

### 4.2 Stage 2: archetype guidance (code, no LLM)

`archetypes.py` holds a dict: archetype id → a short guidance text (5–10 bullet points) of default expectations. The pipeline concatenates the guidance for the archetypes in `spec.archetypes` and inserts it into the draft prompt. This is the MiniAppBench "domain-specific instructions" and the RubricsTree "router", in the simplest form.

Initial archetypes (from §1): `game`, `tracker`, `guide`, `showcase`, `news`, `decision_tool`, `media_player`, `other`. Example guidance for `tracker`:

- Records persist after a page reload.
- The user can create, edit and delete a record.
- An empty state tells the user what to do first.
- Statistics or a summary view reflect the records the user entered.
- A plan that spans days or weeks shows "today" correctly and advances.

Rule: archetype leaves get `origin: "archetype"` and `weight ≤ 3`, unless the query itself implies them (then they are `implicit` with a `covers` id).

### 4.3 Stage 3: K independent drafts (K LLM calls)

Each call gets: query, `as_of`, spec, archetype guidance, schema description, leaf-writing rules (below), and one worked example (one Chinese example, written by hand once, in `prompts.py`).

Diversity: default K = 3 with temperature 0.7 on one model. If `RT_DRAFT_MODELS` lists several models, use one draft per model (WebCoderBench used three LLMs).

Each draft returns the tree plus its own `branch_weight_proposal`. The LLM writes no ids; code assigns them.

Leaf-writing rules (shared by stages 3–5):

1. **Atomic**: one checkable fact per leaf. No "和/并且" joining two checks.
2. **Binary and observable**: a judge answers yes or no from the app. Turn taste into observable proxies. Bad: "页面很美观". Good: "正文文字与背景对比清晰，无重叠或被截断的文字".
3. **Self-contained** (RaR): the leaf makes sense without reading the query.
4. **Functional, not literal** (WebDevJudge failure mode): describe the user-visible effect, not a label, layout, element type or library — unless the user named it. Bad: "有一个名为'今日任务'的卡片". Good: "打开应用即可看到当天要做的学习任务".
5. **Feasible** in the environment profile. Example for a frontend-only profile: do not require live flight prices; require prices labeled as estimates with a date or source.
6. **No uncertain facts in the leaf.** If `generator_confident` is false, write a `verify_by: "fact"` leaf that states what the judge must check. Bad: "列出电影《X》". Good: "列出的电影在 2026 年 10 月前后确实在中国大陆院线上映".
7. **Positive polarity**: pass = good. Write pitfalls as positive leaves (RaR). Example: "预算各项之和与总预算一致".
8. **No double counting**: two leaves must not check the same thing.
9. **Gate sparingly**: `critical: true` only for a leaf whose failure makes the app useless for the user's main goal. At most 5 per tree. Never on a branch root.

### 4.4 Stage 4: merge (one LLM call + code)

LLM input: spec and the K drafts. LLM task: produce one tree that keeps every distinct requirement from any draft, removes duplicates, keeps the clearest wording, and keeps depth ≤ 4. For each leaf, the LLM reports `support` = number of drafts that contain an equivalent leaf (used by the critic; removed before output).

Code after the merge:

- Branch weights: mean of the K `branch_weight_proposal` vectors plus the spec proposal, then normalize to sum 1 (RACE). If any is missing, use the fallback `intention 1, content 2, static 2, dynamic 2`.
- Append the **universal leaves** (RLCF universal items; RCCA runtime gate). They come from `archetypes.py`, not from the LLM. Proposed set:
  - `static`: "页面正常加载，无白屏或阻断使用的报错" (critical), "界面主要文字使用与用户一致的语言".
  - `static`, only if `delivery == "mobile_app"`: "在手机宽度（约 390px）下布局可用，无横向溢出".
- Assign ids.

### 4.5 Stage 5: critic ⇄ revise (≤ 2 rounds, 2 LLM calls per round)

Critic input: query, spec, current tree with ids and `support`. Critic output: a list of issues. Each issue has `leaf_id` (or `null` for a missing leaf), `type`, `severity` (`blocking` | `minor`), `fix` (text).

Issue types, each tied to a source:

| Type | Check | Source |
|---|---|---|
| `missing` | An explicit or implicit requirement has no adequate leaf, or a core flow is not tested end to end | coverage; RaR |
| `not_atomic` | Leaf checks two things | RLCF; PaperBench |
| `subjective` | Leaf needs taste to judge | RaR "objective" |
| `over_specific` | Leaf demands one implementation where others serve the user equally | WebDevJudge §4.3 |
| `too_broad` | Leaf is too vague to fail | WebDevJudge App. B.2 |
| `ungrounded` | Leaf demands a feature with no basis in query or archetype (gold-plating); low `support` is a hint | WebDevJudge App. B.2 |
| `infeasible` | Leaf cannot pass in the environment profile | WebDevJudge feasibility |
| `hardcoded_fact` | Leaf states an uncertain fact as the expected answer | §4.3 rule 6 |
| `duplicate` | Two leaves check the same thing | double counting |
| `weight` | Weights disagree with importance; looks outweigh function when `design_focus` is false; too many `critical` | ARGO; WebDevJudge guideline 2 |
| `wrong_branch` | Leaf in the wrong branch, or `verify_by` is wrong | schema |

If there are no `blocking` issues, stop. Otherwise the reviser gets the tree and the issue list and returns the full revised tree. Code re-assigns ids and runs the critic again (max 2 rounds). Save every round's issues to the case directory; they are useful research data.

### 4.6 Stage 6: deterministic validation ⇄ repair

`schema.validate(record) -> list[str]` returns human-readable errors. Checks:

- JSON shape matches §3; all required fields; types; `weight` in 1–5.
- Four branches present; `dynamic` has exactly two children, basic then complex.
- `content` is empty only if `spec.knowledge_needs` is empty and no requirement mentions content.
- Leaf count 15–40; depth ≤ 4 below each branch root; every internal node has ≥ 1 child.
- Every spec requirement with `importance ≥ 3` is in the `covers` of at least one leaf.
- Every `covers` id exists in the spec. `explicit`/`implicit` leaves have non-empty `covers`.
- Every spec `evidence_quote` is a substring of the query.
- Leaves under `dynamic` have `verify_by == "interaction"`.
- `critical` count ≤ 5; no branch root is critical.
- No two leaves have the same normalized description (strip spaces and punctuation).
- `branch_weights` sum to 1 ± 1e-6.

On errors, call the LLM once with the tree and the error list ("fix only these errors"). Max 2 repair attempts. If still invalid, write the case to `failed.jsonl` with the errors and continue with the next case.

JSON parsing: request JSON output mode when the endpoint supports it; else extract the first fenced or bare JSON object. On a parse failure, retry the same call up to 3 times (WebDevJudge raises temperature by 0.1 each retry; do the same).

### 4.7 Run directory and resume

```
runs/<run_name>/
  config.json
  rubrics.jsonl            # final, one line per valid case
  failed.jsonl
  cases/<case_id>/
    spec.json  draft_1.json … draft_K.json  merged.json
    critic_1.json  revised_1.json  critic_2.json …
    final.json  calls.jsonl   # every prompt, response, model, usage, latency
```

A case with `final.json` is skipped on rerun unless `--force`. `rubrics.jsonl` is rebuilt from all `final.json` files at the end of a run, so the order is the input order.

### 4.8 Baseline method: `--method webdevjudge_baseline`

One LLM call per query, with a prompt that follows the WebDevJudge Appendix B.2 structure (three branches, basic/complex, binary leaves, one example). Output converted to our schema: `content` empty, all `weight = 1`, `critical = false`, `origin = "explicit"`, `covers = []`, branch weights 1/3/2 normalized (without content). Validation for the baseline uses the WebDevJudge structural check only.

Purpose: the comparison point for Phase 2. Note: the WebDevJudge repo has no license file. Write our own prompt that follows the published structure; do not copy their file into this repo.

## 5. Reference scorer (`score.py`, about 40 lines)

Single-answer mode only. Input: tree and a map `leaf_id → bool`.

- Leaf score = 1 if pass, else 0.
- Internal node score = 0 if any `critical` child scores 0; else Σ(weight·score) / Σ(weight) over children.
- Root score = Σ over branches of `branch_weights[b] · score(b)`; a branch with no leaves is skipped and the weights re-normalized.
- Also return per-branch scores and the list of failed critical leaves.

Pairwise scoring and the judge prompts are not in scope. A pairwise judge can use per-leaf A/B/tie with the same weights (WebDevJudge style).

## 6. Code layout

Match the sibling project `multiturn-query-generation`: OpenAI-compatible client, configuration from environment variables, dataclasses, offline tests with fakes.

```
rubrics-tree-generation/
  PLAN.md
  README.md                 # how to run; written at the end
  requirements.txt          # openai>=1.0  (pytest for tests)
  .env.example              # RT_BASE_URL, RT_API_KEY, RT_MODEL, RT_DRAFT_MODELS (optional), RT_CRITIC_MODEL (optional)
  rubric_tree/
    __init__.py
    __main__.py             # CLI, see below
    schema.py               # Node, RubricRecord dataclasses; from_dict/to_dict; assign_ids; validate
    archetypes.py           # archetype ids, guidance texts, universal leaves
    prompts.py              # SPEC, DRAFT, MERGE, CRITIC, REVISE, REPAIR, BASELINE templates + the one worked example
    llm.py                  # async client: chat_json(messages, model, temperature) -> (obj, usage); JSON extraction; retries; logs to calls.jsonl
    pipeline.py             # one function per stage; run_case(); run_all() with asyncio semaphore (default 8)
    score.py                # §5
    export.py               # to_webdevjudge(record); to_markdown(records) for manual review
    stats.py                # leaves per branch, depth, origin mix, verify_by mix, critical count, weights
  tests/
    fakes.py                # FakeLLM: returns canned JSON per stage, can inject bad JSON
    test_schema.py  test_pipeline.py  test_score.py  test_export.py
```

CLI:

```bash
python -m rubric_tree generate --input genwebapp_v50.jsonl --run-name v1 \
    [--method full|webdevjudge_baseline] [--as-of 2026-10-09] [--drafts 3] [--critic-rounds 2] \
    [--env-profile frontend_static] [--ids case-06,case-13] [--concurrency 8] [--force]
python -m rubric_tree stats   runs/v1/rubrics.jsonl
python -m rubric_tree export  runs/v1/rubrics.jsonl --format markdown|webdevjudge --out <path>
```

The prompts are the most important part. The implementer must write them in `prompts.py` with the rules from §4.1, §4.3 and §4.5 included literally, and must write the one worked example by hand (a full tree for one query that is **not** in the 26 cases, so that the example does not leak into the evaluation).

## 7. Phases and acceptance criteria

### Phase 1: core pipeline (implement now)

| Step | Verify |
|---|---|
| 1. `schema.py` + `score.py` + tests | `pytest tests/test_schema.py tests/test_score.py`: each validator rule has one failing fixture; gate semantics (critical child fails → parent 0; skipped empty branch) |
| 2. `llm.py` + `FakeLLM` | Test: bad JSON then good JSON → success after retry; usage logged |
| 3. `archetypes.py` + `prompts.py` | Review by the user (prompts are research decisions) |
| 4. `pipeline.py` stages 1–6 + baseline | `pytest tests/test_pipeline.py` with FakeLLM: end-to-end writes all artifacts; resume skips finished cases; invalid case goes to `failed.jsonl` |
| 5. `export.py` + `stats.py` | Test: `to_webdevjudge` output passes a re-implementation of WebDevJudge `verify_tree_structure` |
| 6. Real run on 5 cases: 06, 13, 15, 16, 18 (both methods) | All valid; the user reads the Markdown export and accepts or gives feedback |
| 7. Real run on all 26 cases | 26/26 valid, or every failure explained; `stats` output in README |

### Phase 2: evaluate the generator (after Phase 1 review)

1. **Manual leaf audit.** Export a sample of 100 leaves (mixed methods, blind to method). The user labels each leaf: atomic? objective? over-specific? grounded? A label sheet is enough. Compare `full` vs `webdevjudge_baseline`.
2. **Stability.** Generate twice with different seeds. An LLM aligns leaves of run A to run B. Report matched-leaf precision and recall per branch.
3. **Ablations.** Turn off one stage at a time: no spec (draft from query only), K = 1, no critic. Measure with (1) and (2).
4. **Perturbation test** (interventional-transfer idea). For a few generated apps, make controlled defects (remove persistence, break one button, change a fact, break the budget sum) and controlled improvements. Check that a fixed judge with the tree fails the right leaves for defects and passes them for improvements.
5. **Human agreement** (only if apps and human pairwise labels exist, for example from `ddb-comparison-rating`). Same judge and model, rubric from `full` vs baseline vs no rubric. Report agreement with humans, as in WebDevJudge Table 3.

### Phase 3: optional extensions (only if Phase 2 shows a need)

- **Knowledge grounding**: a search tool fills `knowledge_needs` with dated facts before drafting (RaR shows reference material improves rubrics). Needed if fact leaves are too vague.
- **Contrastive refinement** (RLCF candidate-based, OpenRubrics CRG): give the critic 2–4 generated apps (code + screenshot) for the same query; add leaves for real failure modes seen in them; drop leaves that never separate apps, if the use is pairwise.
- **Preference-consistency filter** (OpenRubrics): keep a tree only if a judge with it predicts the human label.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Implicit requirements become gold-plating | `rationale` required; critic `ungrounded` check; draft `support`; Phase 2 audit |
| Leaves demand one implementation | Rule 4; critic `over_specific`; `note` field for accepted alternatives |
| Wrong facts in leaves | Rule 6; `generator_confident`; `verify_by: fact` |
| One model's blind spots in all drafts | Option for several draft models; Phase 2 stability check |
| Static/looks dominate the score | Branch weight bounds checked by the critic when `design_focus` is false (ARGO) |
| Gates make scores too harsh when a judge errs on one leaf | Max 5 critical leaves; never on branch roots; revisit in Phase 2 |

## 9. Open questions for the reviewer (defaults in bold)

1. **Downstream use.** Is the tree for evaluation (single or pairwise judge), for RL reward, or both? Default: **evaluation, both modes**. RL use would need stricter atomicity and the Phase 3 contrastive filter.
2. **Environment profile.** What can the generated app use? Default: **frontend only (HTML/CSS/JS, localStorage, public CDNs and public APIs, no backend)**. The `ddb-comparison-rating` criteria mention "real integration", so DeepDiver apps may have a backend. If yes, persistence and data leaves change.
3. **Rubric language.** Default: **leaf descriptions in Chinese** (the query language), field names in English. Alternative: English leaves for non-Chinese judges.
4. **Models.** Which OpenAI-compatible endpoint and models can the pipeline use? Is a search tool available (Phase 3)? Default: **one strong reasoning model for all stages, no search**.
5. **Branch set.** Accept the fourth branch `content`? Default: **yes**. `export --format webdevjudge` merges it into `static` for compatibility.
6. **Human labels.** Do generated apps and human preferences exist for these 26 queries? This decides if Phase 2 step 5 is possible.

## 10. Considered and not included

- **Requirement dependencies** (DevAI DAG, Mind2Web 2 sequential nodes): a judge usually fails a dependent flow anyway. Add only if Phase 2 shows double penalties or false passes.
- **Negative-point criteria** (HealthBench): replaced by positive-polarity leaves to keep one aggregation rule.
- **Trained rubric generator** (GenRubric, Rubric-ARM, OpenRubrics Rubric-RM): needs training data we do not have yet. Phase 1–2 outputs could become that data.
- **Implicit aggregation** (RaR found a single holistic judge score with the rubric can beat explicit sums): this is a judge choice, not a generator choice. The tree supports both.
