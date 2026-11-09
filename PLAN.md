# Rubric-tree generation for web-app queries: design and implementation plan

Status: draft for review. Do not implement until the open questions in §9 have answers or the defaults are accepted.
Date: 2026-10-09.

## 0. Goal

Input: one web-app generation query (one line of `genwebapp_v50.jsonl`: `{"id", "prompt"}`).
Output: one **rubric tree** for that query. A judge (LLM, agent or human) uses the tree to grade a generated app, or to compare two apps.

The pipeline makes the tree. The judge is out of scope. The plan includes a small reference scorer only so that the tree semantics (gates) are defined and testable.

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

- **Requirements that follow from personal context.** Examples: "高血糖父母" means low-sugar dishes with low glycemic index. "小孩两岁半" means child-friendly travel. "长期用" means persistence. The WebDevJudge prompt extracts only what the query states. We must also extract what it implies. (Since 2026-10-16 these count as explicit, with the quoted words as evidence; see §4.1.)
- **Content quality is often the main value.** For a travel guide, correct and useful information matters more than buttons. WebDevJudge puts content under `static`, mixed with "element is present". We give content its own branch.
- **Freshness and real-world facts.** "近期在映热门电影", "最近3年", "国庆节", "今年". The correct content depends on a date. The rubric generator may not know the facts. It must not write facts it is not sure of into leaves.

## 2. Related work and what we borrow

| Work | Institution | Idea we take | Where in pipeline |
|---|---|---|---|
| **WebDevJudge** (ICLR 2026, [arXiv 2510.18560](https://arxiv.org/abs/2510.18560), [code](https://github.com/lcy2723/WebDevJudge)) | Tencent AI Lab, HKUST, NTU | Query-grounded rubric tree with `intention` / `static` / `dynamic(basic, complex)`; binary atomic leaves; branch weights 1/3/2; the "functional equivalence" guideline; generated rubrics are "too specific or too broad" on vague queries; judge failure modes (literal reading, feasibility, position bias); pairwise > single grading | Base schema (§3); baseline method (§4.8); critic checks (§4.5) |
| **MiniAppBench / MiniAppEval** (ICML 2026, [arXiv 2603.09652](https://arxiv.org/abs/2603.09652)) | Inclusion AI (Ant Group), SJTU, CMU | Same three dimensions on real assistant queries; expert-written **domain-specific guidelines** given to the generating LLM; the reference is "a flexible inspection guide rather than a rigid template"; removing the reference cuts judge recall from 85% to 46% | Archetype guidance (§4.2) |
| **RubricsTree** ([arXiv 2606.18203](https://arxiv.org/abs/2606.18203)) | Google et al. | Taxonomy of atomic Boolean rubrics (the paper calls it evolving) plus a router that activates only the relevant ones per query | Archetype routing (§4.1, §4.2) |
| **PaperBench** ([arXiv 2504.01848](https://arxiv.org/abs/2504.01848)) | OpenAI | Weighted tree; weight is importance **relative to siblings**; decompose until an expert can check a leaf quickly; parent score = weighted mean of children | Leaf size rule; scorer (§3, §5). Node weights removed 2026-10-20 |
| **Mind2Web 2** ([arXiv 2506.21506](https://arxiv.org/abs/2506.21506)) | OSU | **Critical** nodes gate the parent ("gate-then-average"); non-critical nodes give partial credit | `critical` flag; scorer (§3, §5) |
| **RCCA** ([arXiv 2608.27906](https://arxiv.org/abs/2608.27906)) | Inclusion AI (Ant Group) | Web-app rubrics split into **initial-state** vs **after-interaction**; severity penalties by item level (reward = 0.2 + 0.8 × (1 − penalty)); format/source/runtime gates before rubric checks (reward 0 / 0 / 0.1). Paper title: "Design the Feedback, Not Just the Reward". The review of 2026-10-20 found no score ceiling | `verify_by` field; universal leaves (§4.4) |
| **Rubrics as Rewards (RaR)** ([arXiv 2507.17746](https://arxiv.org/abs/2507.17746)) | Scale AI | Desiderata: expert grounding, coverage, importance weights, **self-contained** items; Essential/Important/Optional/Pitfall; 7–20 items; pitfalls phrased positively; reference material improves rubrics; stronger generators make better rubrics | Leaf rules; all leaves positive |
| **OpenRubrics / CRG** ([arXiv 2510.07743](https://arxiv.org/abs/2510.07743)) | Emory et al. | Split **hard rules** (explicit) from **principles** (implicit); contrastive generation from good vs bad responses; keep rubrics that predict the human preference label | `origin` field (§3); Phase 3 contrastive stage |
| **RLCF, "Checklists are better than reward models"** ([arXiv 2507.18624](https://arxiv.org/abs/2507.18624)) | CMU, Apple | Candidate-based checklists (from real failure modes) are more objective, atomic and complete than direct prompting; fixed **universal** items added to every checklist | Universal leaves (§4.4); Phase 3 |
| **DeepResearch Bench / RACE** ([arXiv 2506.11763](https://arxiv.org/abs/2506.11763)) | USTC et al. | Fixed top-level dimensions, **task-adaptive dimension weights**, averaged over several LLM trials | Considered. Branch weights removed 2026-10-23 |
| **WebCoderBench** ([arXiv 2601.02430](https://arxiv.org/abs/2601.02430)) | PKU | Separate functional / visual / **content** alignment; checklists drafted by **3 different LLMs**, then merged | `content` branch; multi-draft merge (§4.3, §4.4) |
| **ARGO** ([OpenAI alignment blog](https://alignment.openai.com/argo/)) | OpenAI | Frontend reward models over-weight layout and typography; one page with broken buttons was preferred for its layout | Critic check: function must outweigh looks (§4.5) |
| **Agent-as-a-Judge / DevAI** ([arXiv 2410.10934](https://arxiv.org/abs/2410.10934)) | Meta, KAUST | Requirements vs softer preferences; dependencies between requirements | Considered; dependencies deferred (§10) |
| **HealthBench** ([arXiv 2505.08775](https://arxiv.org/abs/2505.08775)) | OpenAI | Per-conversation rubrics; axis tags such as accuracy, completeness, context awareness | `content` sub-structure; implicit-context leaves |
| **Interventional transfer** ([arXiv 2610.10809](https://arxiv.org/abs/2610.10809)) | — | Validate a rubric with perturbations: a rubric that catches defects may still fail to reward improvements; test both directions | Phase 2 perturbation test (§7) |

Summary of the design position: keep the WebDevJudge tree as the base, because WebDevJudge and MiniAppBench both validated it against humans. Add four things the data needs: (1) a query-analysis stage for explicit and implicit requirements, (2) archetype guidance, (3) a content branch with fact-check rules, (4) multi-draft merge plus a critic loop for coverage and over-specificity.

## 3. Output schema

One JSON object per query. Output file: `rubrics.jsonl`, one line per case.

```jsonc
{
  "id": "case-06",
  "prompt": "我想做一份适合高血糖父母的家常菜谱……",
  "as_of": "2026-10-09",                  // the case's as_of, else --as-of; spec.time_frame has the user's today
  "method": "full",                       // "full" | "webdevjudge_baseline"
  "spec": { ... },                        // output of stage 1, see §4.1
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
| `critical` | bool | Leaves only. A hard boundary: if this leaf fails, the whole app scores 0 (decided 2026-10-20; Mind2Web 2 gates only the parent). Default false. |
| `children` | list[Node] \| null | null for a leaf. |
| Leaf only: `origin` | enum | `explicit` (stated in query) \| `implicit` (must-be quality: inferred from query context or from what every product of this kind has) \| `attractive` (a feature the user did not ask for but would value; at most 4 per tree, never critical) \| `archetype` (default expectation for the app type) \| `universal` (fixed, added by code). |
| Leaf only: `covers` | list[str] | Spec requirement ids (`R1`, `R2` …) that this leaf checks. Required for `explicit`, `implicit` and `attractive`. An `attractive` leaf covers only attractive requirements, and only attractive leaves cover them. |
| Leaf only: `verify_by` | enum | `view` (visible on load or in code) \| `interaction` (needs user actions; RCCA "dynamic") \| `fact` (needs external knowledge or search to check). |
| Leaf only: `note` | str, optional | Guidance for the judge: tolerance, accepted alternatives. Example: "任何清晰标注血糖友好的方式都可以，如标签、图标或分类". |

Branch meaning:

- `intention`: the core goals. "Does this app do what the user wanted at all?"
- `content`: the information the app shows. Accuracy, completeness, fit to the user's context, internal consistency (sums, dates), freshness. Empty only if the spec says the query has no content needs (for example a pure chess game).
- `static`: visible structure and look on load. Required sections and elements, readable layout, mobile layout when the user said "APP", visual style when the user asked for one.
- `dynamic.basic`: single-step interactions (tap, type, select, play).
- `dynamic.complex`: multi-step flows and state changes (create → reload → still there; finish a game; switch person and see other data).

Size target: 15–40 leaves in total, depending on query complexity. There are no leaf counts per branch (decided 2026-10-26; WebDevJudge has none). Max depth 4 below a branch root. WebDevJudge averaged 29.9 leaves and height 5.

### Worked example (fragment, case-06)

```jsonc
"content": {"id": "C", "description": "菜谱内容", "critical": false, "children": [
  {"id": "C.1", "description": "每道菜都适合高血糖人群：主料避免高糖、精制主食为主的做法，或给出替换建议",
   "critical": true, "origin": "implicit", "covers": ["R2"], "verify_by": "fact", "children": null},
  {"id": "C.2", "description": "菜品使用普通菜市场或超市容易买到的食材", "critical": false,
   "origin": "explicit", "covers": ["R3"], "verify_by": "view", "children": null},
  {"id": "C.3", "description": "每道菜有分步骤的做法说明", "critical": false,
   "origin": "explicit", "covers": ["R4"], "verify_by": "view", "children": null}
]},
"dynamic": {"id": "D", "children": [
  {"id": "D.B", "description": "基础交互", "children": [
    {"id": "D.B.1", "description": "用户可以浏览菜品并选中一道菜查看详情", "origin": "explicit", "covers": ["R5"], "verify_by": "interaction", ...}]},
  {"id": "D.C", "description": "复杂交互", "children": [
    {"id": "D.C.1", "description": "用户把菜品加入家庭菜单后刷新页面，菜单仍然保留", "critical": true,
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

Inputs: query, `as_of` date (the `as_of` field of the input case, else `--as-of`, else the run date), environment profile (§9 Q2).
Output (JSON):

```jsonc
{
  "archetypes": ["tracker", "guide"],          // 1–3 ids from the fixed list in archetypes.py
  "delivery": "mobile_app" | "single_page" | "unspecified",
  "ui_language": "zh",
  "design_focus": false,                       // true only if the query asks for a look or mood (case-10 "竹林幽静氛围")
  "time_frame": {"date": "2026-10-09"},        // the user's today, and refers_to: the period the query is about (see the rules below)
  "requirements": [
    {"id": "R1", "type": "explicit", "text": "推荐书籍", "evidence_quote": "要能推荐书籍", "critical": true},
    {"id": "R2", "type": "explicit", "text": "推荐的书与教育孩子和管理相关", "evidence_quote": "启迪我教育小孩的、以及做好管理者的书籍", "critical": true},
    {"id": "R3", "type": "explicit", "text": "进度支持一年 24 本的目标", "evidence_quote": "今年读完 24 本书", "critical": false}
  ],
  "knowledge_needs": [                         // facts the app must show and a judge must check
    {"topic": "国庆期间海南亲子景点与天气", "generator_confident": false}
  ]
}
```

Rules in the prompt:

- Three requirement types, after the Kano model of product quality (decided 2026-10-30): what the user asked for, what the user takes for granted, and what the user did not expect but values. Reason: in `dsv4-rand100-max-t1` the implicit requirements (3.0 per case) only filled gaps in the core function (for a Canva clone: "text can be edited", "images can be uploaded"), and the critic removed leaves such as sample data on first open as `ungrounded`. A tree that checks only the core function cannot tell a working app from a thoughtful one.
- Explicit requirement = stated in the query, or follows directly from words in the query. `evidence_quote` is those words and must be an exact substring of the query (code checks this).
- Implicit requirement (Kano must-be quality) = a need that no words in the query state, but that a typical user with this request takes for granted: if it is missing, the user is let down; if it is there, the user does not notice. Two sources: this user's context (OpenRubrics "principles"; HealthBench "context awareness"), and what every competent product of this kind has today (an editor can undo; the user can edit and delete what they added; a delete asks for confirmation or can be undone; invalid input gets a clear message). Only the must-be qualities that the main flows need. A `rationale` cites the context or the kind of product.
- Attractive requirement (Kano attractive quality) = a feature that no words in the query state and that the user would not miss, but would notice and value, because it serves this user's goal or the next thing the user does with the result. The `rationale` names the words of the query it serves. Example: a daily news digest to post in a WeChat group gets one-click copy, ready to paste. 0–4 per query (code checks the spec and the tree); 0–1 is normal for a simple or narrow request; none that goes against a stated wish ("简单", "别的都不用"). Never critical: a user is not let down by a feature they did not expect. Specific to the query, not a feature for any app ("深色模式"); a quality that users of this kind of product take for granted today is implicit. A user-visible result, not a mechanism. Each one gets exactly one leaf with `origin: "attractive"`; otherwise attractive leaves are normal leaves with the same weight (decided 2026-10-30). The cap of 4 lets an app that does only what was asked pass at least 73% (4 of 15 leaves) to 90% (4 of 40) of the leaves, so attractive features separate good apps from thoughtful ones without outweighing the request.
- The bar for explicit and implicit requirements: if the app does not meet it, the user's goal fails or the user is let down. A feature that is only nice to have is not an explicit or implicit requirement; it can be attractive.
- Make each requirement one need: no "or" lists, no "最好" or "ideally".
- `critical` uses the **critical bar** (`prompts.CRITICAL_BAR`, shared with leaf rule 9; decided 2026-10-23): a requirement or a leaf is critical only if failing it, by itself, badly hurts the user's experience or the user's view of the result. Test: think of an app that does everything else well but fails this one. If the user would call that app broken, wrong, or not what they asked for, it is critical. If the user would only find it weaker, less complete or less polished, it is not critical. A nice-to-have feature is never critical. This replaced a 1–5 `importance` score (decided 2026-10-20): two tiers, as for leaves. A critical leaf must cover a critical requirement.
- Do not write requirements for the environment profile, or for what the universal leaves check (page loads, UI language, mobile width).
- Write `text` and `rationale` in the language of the query.
- `time_frame` (decided 2026-10-23): when the user wrote the query, and the period it is about.
  - `date`: the user's today, the day the user wrote the query, not the time of the events in it. It is `as_of`, unless the query's own words show that the user wrote at another time: an event, a year or a season that does not fit `as_of`. Work it out from the relative words. Example: `as_of` is 2026-10-23 and the query says "明年巴黎奥运会". The Paris Olympics were in 2024 and "明年" is the next year, so the user wrote in 2023: the date is "2023", not "2024". Such a date is "YYYY", "YYYY-MM" or "YYYY-MM-DD", as exact as the query shows, with an `evidence_quote` (an exact substring of the query, checked by code) and a `rationale`.
  - `refers_to`: only if the query is about a dated event or period: that period in absolute dates. Example: "2024年7-8月，巴黎奥运会".
  - When the date is `as_of`, the spec has `{"date": as_of}`, plus `refers_to` if the query has one.
  - Reason: the queries were written at different times, and the input has no date for them. In half-b, d842476807c5 ("明年世界杯 … 这届横跨美加墨") and 50d04c1169b4 ("明年（2026年）") were written in 2025, 3ae4225fbce0 ("去年(2025)") in 2026. The dates in the `sources` folder names are when the trajectories ran, not when the query was written. A first prompt without `refers_to` and with a same-year example ("今年巴黎奥运会") made Qwen3.8-27B write the year of the event, not the year the user wrote ("2026" for d842476807c5 and 64d485e364d0).
- Resolve calendar words ("今天", "明天", "今年", "明年", "下周", "国庆节", "这届") against `time_frame.date` into absolute dates in `text` and `rationale`, as exact as that date allows, and keep the word: "2024年巴黎奥运会（明年）". An `evidence_quote` still copies the query exactly. Keep absolute dates from the query as they are. This replaced "keep relative time words relative; the judge resolves them on the evaluation date" (decided 2026-10-23): resolved on a later date, "明年世界杯" no longer names the 美加墨 World Cup, and half-b-5 mixed the two times in one tree (placeholder knockout pairings next to a check of match results).
- Keep freshness words relative ("最近", "最新", "近期"): the judge checks them on the evaluation date, because the app must be current when it is used.
- Mark `generator_confident: false` for facts the model cannot state with confidence at `time_frame.date`.

### 4.2 Stage 2: archetype guidance (code, no LLM)

`archetypes.py` holds a dict: archetype id → a short guidance text (5–10 bullet points) of default expectations. The pipeline concatenates the guidance for the archetypes in `spec.archetypes` and inserts it into the draft prompt. This is the MiniAppBench "domain-specific instructions" and the RubricsTree "router", in the simplest form.

Initial archetypes (from §1): `game`, `tracker`, `guide`, `showcase`, `news`, `decision_tool`, `media_player`, `other`. Example guidance for `tracker`:

- Records persist after a page reload.
- The user can create, edit and delete a record.
- An empty state tells the user what to do first.
- Statistics or a summary view reflect the records the user entered.
- A plan that spans days or weeks shows "today" correctly and advances.

Rule: archetype leaves get `origin: "archetype"`, unless the query itself implies them (then they are `implicit` with a `covers` id).

### 4.3 Stage 3: K independent drafts (K LLM calls)

Each call gets: query, the user's today (`spec.time_frame.date`), spec, archetype guidance, schema description, leaf-writing rules (below), and one worked example (one Chinese example, written by hand once, in `prompts.py`).

Diversity: default K = 3 with temperature 0.7 on one model. If `RT_DRAFT_MODELS` lists several models, use one draft per model (WebCoderBench used three LLMs).

Each draft returns the tree. The LLM writes no ids; code assigns them.

Leaf-writing rules (shared by stages 3–5):

1. **Atomic**: one checkable fact per leaf. If a real app can pass one part of a leaf and fail another, split the leaf. No "和/并且" joining two checks.
2. **Binary and observable**: a judge answers yes or no from the app. Observable defects (overlapping or cut-off text, low contrast) are normal leaves. When design_focus is false, code adds one universal leaf for overall visual quality: do not write your own generic look leaf (Bad: "页面很美观"). When design_focus is true, write yes/no leaves for the look the user asked for, each with a note that tells the judge what to look at. Example: "页面整体呈现复古像素游戏风格", note "看字体、图标和边框是否为像素风格".
3. **Self-contained** (RaR): the leaf makes sense without reading the query.
4. **Functional, not literal** (WebDevJudge failure mode): describe the user-visible effect, not a label, layout, element type or library — unless the user named it. Bad: "有一个名为'今日任务'的卡片". Good: "打开应用即可看到当天要做的学习任务".
5. **Feasible** in the environment profile. Example for a frontend-only profile: do not require live flight prices; require prices labeled as estimates with a date or source.
6. **Correct facts, but no uncertain facts in the leaf.** When the app must show facts (the spec has `knowledge_needs`), write `verify_by: "fact"` leaves that check that the facts the user's goal depends on are correct (for example rules, prices, dates, names). If `generator_confident` is false, write a `verify_by: "fact"` leaf that states what the judge must check. Bad: "列出电影《X》". Good: "列出的电影在评测时确实在中国大陆院线近期上映". Dates follow the spec: write the absolute dates that the spec resolved against `time_frame.date`, the user's today. Do not require a fact that became known after that date (for example the results of matches played later). Do not fail an app for showing such a fact when it is correct: a leaf about it accepts both what was known at that date (待定, placeholders) and the correct later fact (decided 2026-10-23; in half-b-asof, d842476807c5 C.9 required 待定 for every 2026 World Cup result, so an app with the real results failed).
7. **Positive polarity**: pass = good. Write pitfalls as positive leaves (RaR). Example: "预算各项之和与总预算一致".
8. **No double counting**: no two leaves may be duplicates, in the same branch or in different branches. Two leaves are duplicates when they measure the same thing, or when every app that passes one also passes the other and every app that fails one also fails the other. Keep one of them. Common cases: one feature split into steps that pass or fail together (for example a music player that can play, pause and resume: keep one leaf); the same check again in a later flow, with nothing new to check. A single step and a longer flow that contains it are not duplicates: the flow can fail after the step works. An intention leaf can overlap the detailed leaves that check its goal: that is not double counting. Reason: every leaf has the same weight (§5), so the number of leaves for a need is its weight (decided 2026-10-23). The two-way test replaced "an app that passes one almost always passes the other" (decided 2026-10-23, evening): the one-way test made a single step a duplicate of any flow that contains it, and merges emptied the basic group.
9. **Gate by the critical bar** (§4.1): a failed critical leaf sets the whole score to 0. Mark a leaf critical only if it meets the bar by itself and covers at least one critical requirement. When several leaves cover the same critical requirement, mark only the leaf that checks its core. A judge must be able to decide a critical leaf without taste: never mark a look or style leaf critical. At most 5 per tree: this is a limit, not a target, and fewer is normal (in half-b-5 every tree had exactly 5). Never on a branch root.

No generator values as the bar (decided 2026-10-26, after a review of `dsv4-rand100-max-t1`). A leaf states what the judge checks, not the generator's answer. Where reputable sources differ, the leaf checks agreement with an authoritative source (rule 6). A critical leaf states no value that is not in the query (rule 9). A spec requirement states the need, not values. Reason: in 9a30f4d85108, critical I.4 required 37–40℃, 10–20 minutes and 2–4 times a day, so an app that follows another reputable source scored 0.

### 4.4 Stage 4: merge (one LLM call + code)

LLM input: spec and the K drafts. LLM task: combine the drafts into one tree that keeps every check from any draft, writes duplicates (rule 8) as one leaf with the clearest wording, also when drafts word or place a check differently, keeps the checks with the highest support if more than 40 leaves remain, sets each critical flag by rule 9 instead of copying the drafts' flags, and keeps depth ≤ 4. (Decided 2026-10-23, evening: a "fewest leaves" merge, used for one day, made the merged tree smaller than the average draft, 0.86–0.90× against 1.07× before, and emptied dynamic groups.) For each leaf, the LLM reports `support` = number of drafts that contain an equivalent leaf (used by the critic; removed before output).

Code after the merge:

- Append the **universal leaves** (RLCF universal items; RCCA runtime gate). They come from `archetypes.py`, not from the LLM. Proposed set:
  - `static`: "页面正常加载，无白屏或阻断使用的报错" (critical), "界面主要文字使用与用户一致的语言".
  - `static`, only if `delivery == "mobile_app"`: "在手机宽度（约 390px）下布局可用，无横向溢出".
  - `static`, only if `design_focus` is false: "界面视觉设计精致统一，看起来是经过设计的完整产品" (note: "看配色、字体、间距是否统一，信息层次是否清楚。只是没有错乱或重叠不算通过。"). When `design_focus` is true, the query's own style leaves replace it. The bar is high on purpose: the hygiene leaves already set the minimum, and a pairwise judge gets signal only when one app passes and the other fails.
- Assign ids.

### 4.5 Stage 5: critic ⇄ revise (1 round by default, 2 LLM calls per round)

Critic input: query, spec, current tree with ids and `support`. Critic output: a list of issues. Each issue has `leaf_id` (or `null` for a missing leaf), `type`, `severity` (`blocking` | `minor`), `fix` (text).

Issue types, each tied to a source:

| Type | Check | Source |
|---|---|---|
| `missing` | A spec requirement has no adequate leaf, a core flow is not tested end to end, or the tree checks only the core function and misses a must-be quality of this kind of product that the main flows need (fix: an archetype leaf) | coverage; RaR; Kano must-be |
| `not_atomic` | Leaf checks two things | RLCF; PaperBench |
| `subjective` | A look leaf without a note that tells the judge what to look at, or a generic look leaf that repeats the universal one | RaR "objective" |
| `over_specific` | Leaf demands one implementation where others serve the user equally | WebDevJudge §4.3 |
| `too_broad` | Leaf is too vague to fail | WebDevJudge App. B.2 |
| `ungrounded` | Leaf demands a feature with no basis in query, archetype or an attractive requirement (gold-plating); low `support` is a hint. An attractive leaf that covers an attractive requirement is grounded: the critic rewrites a weak one, it does not remove it | WebDevJudge App. B.2 |
| `infeasible` | Leaf cannot pass in the environment profile, requires a fact that was not known at the user's today (`spec.time_frame.date`), or fails an app that shows such a fact correctly | WebDevJudge feasibility |
| `hardcoded_fact` | A leaf or a note states a fact as the expected answer, and the fact is wrong or uncertain. The critic checks every number, name, date and rule itself; `generator_confident` is not proof | §4.3 rule 6 |
| `duplicate` | Two leaves are duplicates by rule 8, in the same branch or in different branches | double counting |
| `contradiction` | Two leaves, or a leaf and a note, disagree: one requires something that another calls optional or lets pass without it | consistency |
| `balance` | A `critical` flag fails the critical bar (too loose or too strict); a critical leaf is a look or style leaf; look leaves outnumber function leaves when `design_focus` is false | ARGO; WebDevJudge guideline 2 |
| `wrong_branch` | Leaf in the wrong branch, or `verify_by` is wrong | schema |

The critic is told to be strict (decided 2026-10-23; in half-b-5 it found 0–5 issues per tree and no duplicate across branches). It checks every leaf against every rule, then the leaves against each other: all the leaves that cover each requirement (duplicates), every leaf and note against the others (contradictions), every stated fact, and the critical bar on every leaf. Duplicates, contradictions and wrong facts are blocking. An empty issue list is valid only after every leaf was checked.

If there are no issues, stop. Otherwise the reviser gets the tree and the issue list and returns the full revised tree; minor issues also cause a revise (decided 2026-10-20: in v1 the critic found only minor issues, so no tree changed). The reviser applies every blocking issue and each minor issue whose fix is clear. Code re-assigns ids. By default there is 1 round, so the critic does not run again; `--critic-rounds N` runs the critic again until it finds no issues, for at most N rounds. Save every round's issues to the case directory; they are useful research data.

### 4.6 Stage 6: deterministic validation ⇄ repair

`schema.validate(record) -> list[str]` returns human-readable errors. Checks:

- JSON shape matches §3; all required fields; types.
- Four branches present; `dynamic` has exactly two children, basic then complex.
- `content` is empty only if `spec.knowledge_needs` is empty and no requirement mentions content.
- Leaf count 15–40; depth ≤ 4 below each branch root; every internal node has ≥ 1 child. An LLM-written node with `children: []` becomes a leaf only if it has a leaf key (`origin`, `covers`, `verify_by`); an empty group stays a group, so this error reaches the repair step, and for `D.B`/`D.C` it says what kind of leaf to add (decided 2026-10-23: turning an emptied D.B into a leaf made the error unrepairable).
- Every spec requirement is in the `covers` of at least one leaf.
- Every `covers` id exists in the spec. `explicit`/`implicit`/`attractive` leaves have non-empty `covers`.
- At most 4 attractive requirements and at most 4 attractive leaves. Neither is critical. An attractive leaf covers only attractive requirements, and a leaf that covers one has `origin: "attractive"`.
- Every spec `evidence_quote` is a substring of the query.
- `spec.time_frame.date` is "YYYY", "YYYY-MM" or "YYYY-MM-DD". A date other than the record's `as_of` has an `evidence_quote` that is a substring of the query, and a `rationale`. `refers_to`, if present, is a non-empty string.
- Leaves under `dynamic` have `verify_by == "interaction"`.
- `critical` count ≤ 5; only leaves are critical; a critical leaf (except a universal one) covers at least one critical requirement.
- `spec.ui_language` is "zh" or "en".
- No two leaves have the same normalized description (strip spaces and punctuation).

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

One LLM call per query, with a prompt that follows the WebDevJudge Appendix B.2 structure (three branches, basic/complex, binary leaves, one example). Output converted to our schema: `content` empty, `critical = false`, `origin = "explicit"`, `covers = []`. No branch weights: the baseline is scored by the same flat rate as the full method (§5), so only the rubric differs. Validation for the baseline uses the WebDevJudge structural check only.

Purpose: the comparison point for Phase 2. Note: the WebDevJudge repo has no license file. Write our own prompt that follows the published structure; do not copy their file into this repo.

## 5. Reference scorer (`score.py`, about 40 lines)

Single-answer mode only. Input: tree and a map `leaf_id → bool`.

- Leaf score = 1 if pass, else 0.
- Root score = 0 if any `critical` leaf fails. Critical leaves are hard boundaries.
- Else root score = the pass rate over all leaves of the tree. Every leaf has the same weight. Branches and groups do not change the score; they are semantic groups for generation and review (decided 2026-10-23).
- There are no branch weights (removed 2026-10-23). A per-branch mean would give each leaf a weight of 1 / (branches × leaves in its branch), so a leaf in a small branch would count more only because the branch is small.
- There are no node weights, only two tiers: critical and non-critical (decided 2026-10-20).
- How the judge combines the leaf results is not fixed by the generator. Only rules that change what the generator writes (for example the meaning of `critical`) are fixed here.
- Also return per-branch scores and the list of failed critical leaves.

Pairwise scoring and the judge prompts are not in scope. A pairwise judge can use per-leaf A/B/tie (WebDevJudge style).

Nice-to-have features get a leaf only as an attractive requirement (§4.1): at most 4 per tree, never critical (decided 2026-10-30; this replaced "nice-to-have features get no leaves", decided 2026-10-20). Other than those, the tree checks only requirements that pass the bar (§4.1) and the archetype defaults. The pairwise judge finds other extra features by comparing the two apps, and prefers the app whose extras serve the user better (decided 2026-10-20). The judge must not reward an extra that goes against a stated wish (for example more features on a page the user asked to keep "轻量").

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
    stats.py                # leaves per branch, depth, origin mix, verify_by mix, critical count
  tests/
    fakes.py                # FakeLLM: returns canned JSON per stage, can inject bad JSON
    test_schema.py  test_pipeline.py  test_score.py  test_export.py
```

CLI:

```bash
python -m rubric_tree generate --input genwebapp_v50.jsonl --run-name v1 \
    [--method full|webdevjudge_baseline] [--as-of 2026-10-09] [--drafts 3] [--critic-rounds 1] \
    [--env-profile either] [--ids case-06,case-13] [--concurrency 8] [--force]
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
| Attractive requirements reflect the generator's taste, and an RL policy learns to add the same extras to every app | Cap of 4, 0–1 normal for simple requests; `rationale` must name the query words served; no generic features; review the first runs by hand |
| Leaves demand one implementation | Rule 4; critic `over_specific`; `note` field for accepted alternatives |
| Wrong facts in leaves | Rule 6; `generator_confident`; `verify_by: fact` |
| One model's blind spots in all drafts | Option for several draft models; Phase 2 stability check |
| Static/looks dominate the score | Critic `balance` check: look leaves must not outnumber function leaves when `design_focus` is false (ARGO) |
| Gates make scores too harsh when a judge errs on one leaf | Max 5 critical leaves; never on branch roots; revisit in Phase 2 |

## 9. Open questions for the reviewer (defaults in bold)

1. **Downstream use.** Is the tree for evaluation (single or pairwise judge), for RL reward, or both? Default: **evaluation, both modes**. RL use would need stricter atomicity and the Phase 3 contrastive filter. Answer (2026-10-20): **both evaluation and RL reward; the judge is mostly pairwise.**
2. **Environment profile.** What can the generated app use? Answer (2026-10-20): it is not known, so the default profile is **`either`**: the app can be frontend only or full stack, a good app of either kind must be able to pass each leaf, and a leaf requires what only a backend can do only when the user's goal needs it. `frontend_static` and `fullstack` stay available. Earlier default: frontend only. The `ddb-comparison-rating` criteria mention "real integration", so DeepDiver apps may have a backend. If yes, persistence and data leaves change.
3. **Rubric language.** Default: **leaf descriptions in Chinese** (the query language), field names in English. Alternative: English leaves for non-Chinese judges.
4. **Models.** Which OpenAI-compatible endpoint and models can the pipeline use? Is a search tool available (Phase 3)? Default: **one strong reasoning model for all stages, no search**.
5. **Branch set.** Accept the fourth branch `content`? Default: **yes**. `export --format webdevjudge` merges it into `static` for compatibility.
6. **Human labels.** Do generated apps and human preferences exist for these 26 queries? This decides if Phase 2 step 5 is possible.

## 10. Considered and not included

- **Requirement dependencies** (DevAI DAG, Mind2Web 2 sequential nodes): a judge usually fails a dependent flow anyway. Add only if Phase 2 shows double penalties or false passes.
- **Negative-point criteria** (HealthBench): replaced by positive-polarity leaves to keep one aggregation rule.
- **Trained rubric generator** (GenRubric, Rubric-ARM, OpenRubrics Rubric-RM): needs training data we do not have yet. Phase 1–2 outputs could become that data.
- **Implicit aggregation** (RaR found a single holistic judge score with the rubric can beat explicit sums): this is a judge choice, not a generator choice. The tree supports both.
