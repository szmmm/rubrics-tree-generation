"""Prompt templates for every stage, and the one worked example.

These texts are research decisions: review them before a real run. The rules
from PLAN §4.1, §4.3 and §4.5 are included word for word. The worked example
uses a query that is not in genwebapp_v50.jsonl, so it cannot leak into the
evaluation.

Templates use string.Template ($name), because the JSON in them is full of
braces. Do not put a literal dollar sign in a template.
"""
from __future__ import annotations

import json
from string import Template

from .archetypes import ARCHETYPES
from .export import webdevjudge_tree

ENV_PROFILES = {
    "either": (
        "Not known. The app can be frontend only (HTML/CSS/JS in the browser, "
        "with localStorage or IndexedDB, public CDNs and public APIs that need no "
        "private key) or full stack (a frontend and a backend with a database, "
        "which can store data on the server, call external APIs and get live "
        "data). A good app of either kind must be able to pass each leaf: check "
        "what the user sees and does, not where data is stored or fetched. Require "
        "what only a backend can do (for example sync between devices) only when "
        "the user's goal needs it. No app can use the user's own accounts, real "
        "payments or messages to real people. The judge opens the app in a "
        "browser, can click, type and reload, and can read the source code."),
    "frontend_static": (
        "Frontend only. The app is HTML/CSS/JS that runs in the browser. It can "
        "use localStorage or IndexedDB, public CDNs, and public APIs that need no "
        "private key. It has no backend server and no private API keys, so it "
        "cannot get live data that needs a key (flight prices, paid feeds) or "
        "send notifications from a server. The judge opens it in a browser, can "
        "click, type and reload, and can read the source code."),
    "fullstack": (
        "Full stack. The app has a frontend and a backend with a database, and "
        "is served at a preview URL. It can store data on the server, call "
        "external APIs from the server and get live data. It cannot use the "
        "user's own accounts, real payments or messages to real people. The "
        "judge opens it in a browser, can click, type and reload, and can read "
        "the source code."),
}

# ── shared rule blocks ───────────────────────────────────────────────────────

SCHEMA = """\
## Rubric tree format

The tree has four branches. A branch root is {"description": "...", "children": [...]}.

- intention (3-6 leaves): the core goals. "Does this app do what the user wanted at all?"
- content (0-15 leaves): the information the app shows. Accuracy, completeness, fit to the user's context, internal consistency (sums, dates), freshness. An empty children list only if the query has no content needs (for example a pure chess game).
- static (4-12 leaves): visible structure and look on load. Required sections and elements, readable layout, mobile layout when the user said "APP", visual style when the user asked for one.
- dynamic: exactly two children, in this order: basic interactions, then complex interactions.
  - basic: single-step interactions (tap, type, select, play).
  - complex: multi-step flows and state changes (create -> reload -> still there; finish a game; switch person and see other data).

Every node below a branch root has these fields:
- description: for a group, a short group name; for a leaf, one yes/no statement.
- critical: true or false. Only a leaf can be critical. A critical leaf is a hard boundary: if it fails, the score of the whole app is 0, whatever the other leaves say.
- children: a list of nodes for a group; null for a leaf.
A leaf also has:
- origin: "explicit" (stated in the query) | "implicit" (inferred from the query's context) | "archetype" (default expectation for this kind of app).
- covers: the spec requirement ids (R1, R2, ...) that the leaf checks. Required for explicit and implicit leaves.
- verify_by: "view" (visible on load or in the code) | "interaction" (needs user actions) | "fact" (needs external knowledge or a search to check). Every leaf under dynamic uses "interaction".
- note (optional): guidance for the judge: tolerance, accepted alternatives.

Do not write ids; code assigns them.
Size: 15-40 leaves in total, depending on how complex the query is. At most 4 levels below a branch root.
If the query implies an archetype expectation, write it as an implicit leaf with a covers id instead.
Every spec requirement is in the covers of at least one leaf.
Write every description and note in the language of the query."""

LEAF_RULES = """\
## Leaf-writing rules

1. Atomic: one checkable fact per leaf. No "和/并且" joining two checks.
2. Binary and observable: a judge answers yes or no from the app. Observable defects (overlapping or cut-off text, low contrast) are normal leaves. When design_focus is false, code adds one universal leaf for overall visual quality: do not write your own generic look leaf (Bad: "页面很美观"). When design_focus is true, write yes/no leaves for the look the user asked for, each with a note that tells the judge what to look at. Example: "页面整体呈现复古像素游戏风格", note "看字体、图标和边框是否为像素风格".
3. Self-contained: the leaf makes sense without reading the query.
4. Functional, not literal: describe the user-visible effect, not a label, layout, element type or library — unless the user named it. Bad: "有一个名为'今日任务'的卡片". Good: "打开应用即可看到当天要做的学习任务".
5. Feasible in the environment profile. Example for a frontend-only profile: do not require live flight prices; require prices labeled as estimates with a date or source.
6. Correct facts, but no uncertain facts in the leaf. When the app must show facts (the spec has knowledge_needs), write verify_by: "fact" leaves that check that the facts the user's goal depends on are correct (for example rules, prices, dates, names). If generator_confident is false, write a verify_by: "fact" leaf that states what the judge must check. Bad: "列出电影《X》". Good: "列出的电影在评测时确实在中国大陆院线近期上映".
7. Positive polarity: pass = good. Write pitfalls as positive leaves. Example: "预算各项之和与总预算一致".
8. No double counting: two leaves must not check the same thing.
9. Gate sparingly: a failed critical leaf sets the whole score to 0. Use critical: true only for a leaf whose failure makes the app useless for the user's main goal. A critical leaf must cover at least one critical requirement. At most 5 per tree. Never on a branch root."""

ISSUE_TYPES = """\
- missing: an explicit or implicit requirement has no adequate leaf, or a core flow is not tested end to end
- not_atomic: the leaf checks two things
- subjective: a look leaf without a note that tells the judge what to look at, or a generic look leaf that repeats the universal one
- over_specific: the leaf demands one implementation where others serve the user equally
- too_broad: the leaf is too vague to fail
- ungrounded: the leaf demands a feature with no basis in the query or the archetype (gold-plating); low support is a hint
- infeasible: the leaf cannot pass in the environment profile
- hardcoded_fact: the leaf states an uncertain fact as the expected answer
- duplicate: two leaves check the same thing
- balance: a critical flag is wrong (the app is still useful when the leaf fails, or the core flow has no critical leaf), there are too many critical nodes, or look leaves outnumber function leaves when design_focus is false
- wrong_branch: the leaf is in the wrong branch, or verify_by is wrong"""

SPEC_RULES = """\
- The bar for every requirement, explicit or implicit: if the app does not meet it, the user's goal fails or the user is let down. A feature that is only nice to have is not a requirement.
- Explicit requirement = stated in the query, or follows directly from words in the query. evidence_quote is those words and must be an exact substring of the query (code checks this). Examples: "高血糖父母" means low-sugar dishes with a low glycemic index; "小孩两岁半" means child-friendly travel; "长期用" means the data persists.
- Implicit requirement = a need that no words in the query state, but that this user needs in this context, with a rationale that cites the context.
- Make each requirement one need: no "or" lists, no "最好" or "ideally". critical: true if the user's goal fails without it, false if the user is only let down without it.
- Do not write requirements for the environment profile, or for what code checks in every app: the page loads, the UI language, the layout at mobile width.
- Write text and rationale in the language of the query.
- Keep relative time words relative ("今天", "今年", "最近3年", "国庆节"): the judge resolves them on the evaluation date. Keep absolute dates from the query as they are.
- knowledge_needs: facts the app must show and a judge must check (prices, schedules, names, events, the rules of a known game). Mark generator_confident: false for facts you cannot state with confidence at as_of.
- archetypes: 1-3 ids from the archetype list, the most important first.
- ui_language: "zh" or "en", the language the user expects in the app.
- delivery: "mobile_app" if the query says APP, app, 手机 or 小程序, or describes use on a phone; "single_page" if it asks for a page or an html page; else "unspecified".
- design_focus: true only if the query asks for a look, a style or a mood."""

SPEC_FORMAT = """\
{
  "archetypes": ["..."],
  "delivery": "mobile_app" | "single_page" | "unspecified",
  "ui_language": "zh",
  "design_focus": false,
  "requirements": [
    {"id": "R1", "type": "explicit", "text": "...", "evidence_quote": "...", "critical": true},
    {"id": "R2", "type": "implicit", "text": "...", "rationale": "...", "critical": false}
  ],
  "knowledge_needs": [
    {"topic": "...", "generator_confident": true}
  ]
}"""

# ── the worked example (written by hand; not one of the evaluation queries) ──

EXAMPLE_QUERY = "帮我做一个管理家里冰箱食材的小应用，记录买了什么、什么时候过期，快过期的要提醒我，还能根据现有食材推荐几道菜。"

EXAMPLE_SPEC = {
    "archetypes": ["tracker", "decision_tool"],
    "delivery": "unspecified",
    "ui_language": "zh",
    "design_focus": False,
    "requirements": [
        {"id": "R1", "type": "explicit", "text": "记录冰箱里有哪些食材",
         "evidence_quote": "记录买了什么", "critical": True},
        {"id": "R2", "type": "explicit", "text": "记录每种食材的过期日期",
         "evidence_quote": "什么时候过期", "critical": True},
        {"id": "R3", "type": "explicit", "text": "提醒用户哪些食材快过期",
         "evidence_quote": "快过期的要提醒我", "critical": True},
        {"id": "R4", "type": "explicit", "text": "根据现有食材推荐菜",
         "evidence_quote": "根据现有食材推荐几道菜", "critical": False},
        {"id": "R5", "type": "implicit", "text": "食材记录长期保存，关闭后再打开仍在",
         "rationale": "管理家里的冰箱是每天持续使用的场景，记录不能在关闭页面后丢失",
         "critical": True},
        {"id": "R6", "type": "implicit", "text": "吃完或扔掉的食材可以从记录中去掉",
         "rationale": "冰箱里的食材会不断被用掉，记录要跟着变化才有用", "critical": False},
    ],
    "knowledge_needs": [
        {"topic": "常见家常菜所需的食材", "generator_confident": True},
    ],
}


def _leaf(description, origin, covers, verify_by, note="", critical=False):
    leaf = {"description": description, "critical": critical,
            "origin": origin, "covers": covers, "verify_by": verify_by}
    if note:
        leaf["note"] = note
    leaf["children"] = None
    return leaf


def _group(description, children):
    return {"description": description, "critical": False,
            "children": children}


EXAMPLE_TREE = {
    "intention": {"description": "核心目标", "children": [
        _leaf("应用能维护一份冰箱现有食材的清单", "explicit", ["R1"], "interaction"),
        _leaf("应用会指出哪些食材快要过期", "explicit", ["R3"], "interaction"),
        _leaf("应用能根据清单里的食材推荐菜", "explicit", ["R4"], "interaction"),
    ]},
    "content": {"description": "推荐内容", "children": [
        _leaf("推荐的每道菜，主要食材都在当前的食材清单里，或明确标出还缺哪些食材", "explicit", ["R4"], "interaction",
              note="盐、油、酱油等常备调料不算缺少的食材"),
        _leaf("推荐的每道菜都是真实存在的家常菜", "explicit", ["R4"], "fact"),
    ]},
    "static": {"description": "页面结构与信息", "children": [
        _group("食材清单", [
            _leaf("每条食材记录显示食材名称", "explicit", ["R1"], "view"),
            _leaf("每条食材记录显示过期日期或剩余天数", "explicit", ["R2"], "view",
                  note="显示具体日期或“还剩 N 天”都可以"),
        ]),
        _leaf("清单为空时，界面提示用户先添加食材", "archetype", [], "view"),
        _leaf("添加食材的入口在首页可以直接找到", "explicit", ["R1"], "view"),
    ]},
    "dynamic": {"description": "交互", "children": [
        _group("基础交互", [
            _leaf("用户填写食材名称和过期日期后，可以把食材加入清单", "explicit",
                  ["R1", "R2"], "interaction", critical=True),
            _leaf("用户可以把吃完或扔掉的食材从清单中移除", "implicit", ["R6"],
                  "interaction", note="删除或标记为已用完都可以"),
            _leaf("用户可以修改已有食材的过期日期", "archetype", [], "interaction"),
            _leaf("用户可以发起推荐，并看到至少一道推荐的菜", "explicit", ["R4"],
                  "interaction"),
        ]),
        _group("复杂交互", [
            _leaf("加入一种明天过期的食材后，打开应用的首屏就能看到它快过期的提醒", "explicit", ["R3"], "interaction",
                  note="横幅、角标、标签、置顶都可以；浏览器通知不是必须的"),
            _leaf("过期日期在一个月以后的食材不会被提醒为快过期", "explicit", ["R3"],
                  "interaction", note="“快过期”的天数由应用决定，1 到 7 天都合理"),
            _leaf("加入食材后刷新页面，食材清单仍然保留", "implicit", ["R5"],
                  "interaction", note="localStorage 或后端保存都可以", critical=True),
            _leaf("清单里的食材变化后，再次推荐的菜随之变化", "explicit", ["R4"],
                  "interaction"),
        ]),
    ]},
}

EXAMPLE_DRAFT = {"branch_weight_proposal": {"intention": 2, "content": 2, "static": 1, "dynamic": 4},
                 "tree": EXAMPLE_TREE}

# ── stage prompts ────────────────────────────────────────────────────────────

_SPEC_SYSTEM = Template("""\
You analyze one request for a web app before anyone writes a rubric for it. Find what the user asked for (explicit requirements), what a reasonable user in this situation also needs (implicit requirements), and which facts a judge must check. Return one JSON object only.

Rules:
$rules

Archetypes:
$archetypes

Output format (JSON):
$format""")

_SPEC_USER = Template("""\
as_of (today): $as_of
Environment profile: $env

User query:
$query""")

_DRAFT_SYSTEM = Template("""\
You write a rubric tree for judging a generated web app against the user's request. A judge (a person or an agent with the running app) answers each leaf with yes or no. Return one JSON object only.

$schema

$leaf_rules

## Worked example (a different query)

Query:
$example_query

Spec:
$example_spec

Output:
$example_draft""")

_DRAFT_USER = Template("""\
as_of (today): $as_of
Environment profile: $env

User query:
$query

Spec (query analysis):
$spec

Default expectations for this kind of app. Use the ones that fit this query; mark them origin "archetype" unless the query implies them:
$guidance

$universal

branch_weight_proposal: the importance 1-5 of each branch for this query: intention (core goals), content (the information the app shows), static (structure and look on load), dynamic (interactions and state changes).

Return JSON:
{"branch_weight_proposal": {"intention": 1-5, "content": 1-5, "static": 1-5, "dynamic": 1-5}, "tree": {"intention": {...}, "content": {...}, "static": {...}, "dynamic": {...}}}""")

_MERGE_SYSTEM = Template("""\
You merge $k draft rubric trees for the same web-app request into one tree. Return one JSON object only.

Task:
- Keep every distinct check from any draft, unless it breaks a rule below.
- Remove duplicates. Where drafts check the same thing, keep the clearest wording, and the critical flag that best fits the spec.
- Keep at most 4 levels below a branch root.
- For each leaf, add "support": the number of drafts (1-$k) that contain an equivalent leaf.

$schema

$leaf_rules""")

_MERGE_USER = Template("""\
as_of (today): $as_of
Environment profile: $env

User query:
$query

Spec:
$spec

$universal

$drafts

Return JSON: {"tree": {"intention": {...}, "content": {...}, "static": {...}, "dynamic": {...}}}""")

_CRITIC_SYSTEM = Template("""\
You review a rubric tree for judging a generated web app. Find the problems that would make a judge give a wrong or unfair verdict, or make the score disagree with what the user wanted. Return one JSON object only.

Issue types:
$issue_types

severity: "blocking" if the issue changes a verdict or the score in a way the user would not accept: a missing core check, a check that a good app can fail, a wrong gate, looks that outweigh function. "minor" if a judge would still read and score the leaf correctly.

Leaves with origin "universal" are fixed by code. Do not report them, except as the other half of a duplicate.
"support" on a leaf is the number of independent drafts that had it.

The tree must follow these rules:

$schema

$leaf_rules

Return JSON: {"issues": [{"leaf_id": "S.2" or null for a missing leaf, "type": "...", "severity": "blocking" | "minor", "fix": "what to change"}]}
An empty issues list is a valid answer.""")

_CRITIC_USER = Template("""\
as_of (today): $as_of
Environment profile: $env

User query:
$query

Spec:
$spec

Tree:
$tree""")

_REVISE_SYSTEM = Template("""\
You revise a rubric tree to fix the issues that a reviewer found. Return one JSON object only.

- Apply every blocking issue. Apply a minor issue when its fix is clear.
- Change nothing else. Keep the wording and support of every leaf that no issue mentions.
- Keep "support" on the leaves you keep; leave it out on new leaves.
- Leaves with origin "universal" are managed by code: leave them unchanged.
- The ids are for reference only; code assigns new ones.

$schema

$leaf_rules""")

_REVISE_USER = Template("""\
as_of (today): $as_of
Environment profile: $env

User query:
$query

Spec:
$spec

Issues:
$issues

Current tree:
$tree

Return JSON: {"tree": {...}}""")

_REPAIR_SYSTEM = """\
You fix a JSON object so that it passes a validator. Fix only the listed errors and change nothing else. Return the full corrected JSON object only."""

_REPAIR_USER = Template("""\
User query:
$query

$context

Errors:
$errors

Object:
$obj""")

_BASELINE = Template("""\
## Task
You are a software quality assurance analyst. Turn a user's request for a web app into a hierarchical rubric. A judge uses the rubric to check a generated web app in a binary way: each requirement is implemented or not implemented.

Return one JSON object with exactly three top-level keys: "intention", "static" and "dynamic".

## Structure
1. Every node is an object with two keys: "description" (a string) and "children" (a list of nodes, or null for a leaf).
2. intention: the purpose and the core goals of the app, as short high-level statements.
3. static: every visible element that needs no interaction. Break each component into its smallest parts (for example, a product card into its image, name and price).
4. dynamic: the interactive behavior. It has exactly two children: first "basic" interactions (single-step actions, such as typing in a field, clicking a button or choosing an option), then "complex" interactions (multi-step processes or actions that change the state of the app, such as submitting a form, filtering a list, or saving data and seeing it again).
5. Every leaf states one specific, atomic and verifiable requirement that a judge can mark as implemented or not implemented.
Write every description in the language of the user's request.

## Example
User request:
$example_query

Rubric:
$example_tree

## User request
$query""")


def spec_messages(query: str, as_of: str, env_profile: str) -> list[dict]:
    archetypes = "\n".join(f"- {aid}: {a['summary']}" for aid, a in ARCHETYPES.items())
    return _messages(
        _SPEC_SYSTEM.substitute(rules=SPEC_RULES, archetypes=archetypes, format=SPEC_FORMAT),
        _SPEC_USER.substitute(as_of=as_of, env=ENV_PROFILES[env_profile], query=query))


def draft_messages(query: str, as_of: str, env_profile: str, spec: dict,
                   guidance: str, universal: list[dict]) -> list[dict]:
    return _messages(
        _DRAFT_SYSTEM.substitute(
            schema=SCHEMA, leaf_rules=LEAF_RULES, example_query=EXAMPLE_QUERY,
            example_spec=_dump(EXAMPLE_SPEC), example_draft=_dump(EXAMPLE_DRAFT)),
        _DRAFT_USER.substitute(
            as_of=as_of, env=ENV_PROFILES[env_profile], query=query, spec=_dump(spec),
            guidance=guidance, universal=_universal_note(universal)))


def merge_messages(query: str, as_of: str, env_profile: str, spec: dict,
                   drafts: list[dict], universal: list[dict]) -> list[dict]:
    blocks = "\n\n".join(f"Draft {i}:\n{_dump(d)}" for i, d in enumerate(drafts, 1))
    return _messages(
        _MERGE_SYSTEM.substitute(k=len(drafts), schema=SCHEMA, leaf_rules=LEAF_RULES),
        _MERGE_USER.substitute(
            as_of=as_of, env=ENV_PROFILES[env_profile], query=query, spec=_dump(spec),
            universal=_universal_note(universal), drafts=blocks))


def critic_messages(query: str, as_of: str, env_profile: str, spec: dict,
                    tree: dict) -> list[dict]:
    return _messages(
        _CRITIC_SYSTEM.substitute(issue_types=ISSUE_TYPES, schema=SCHEMA, leaf_rules=LEAF_RULES),
        _CRITIC_USER.substitute(
            as_of=as_of, env=ENV_PROFILES[env_profile], query=query, spec=_dump(spec),
            tree=_dump(tree)))


def revise_messages(query: str, as_of: str, env_profile: str, spec: dict,
                    tree: dict, issues: list) -> list[dict]:
    return _messages(
        _REVISE_SYSTEM.substitute(schema=SCHEMA, leaf_rules=LEAF_RULES),
        _REVISE_USER.substitute(
            as_of=as_of, env=ENV_PROFILES[env_profile], query=query, spec=_dump(spec),
            issues=_dump(issues), tree=_dump(tree)))


def repair_messages(obj, errors: list[str], *, query: str, kind: str,
                    spec: dict | None = None) -> list[dict]:
    """kind: "spec" (stage-1 output), "tree" ({tree}) or
    "baseline" (a WebDevJudge tree)."""
    if kind == "spec":
        context = (f"The object is a query analysis. Rules:\n{SPEC_RULES}\n\n"
                   f"Format:\n{SPEC_FORMAT}")
    elif kind == "tree":
        context = (f"The object is a rubric tree. Spec (read only):\n{_dump(spec)}\n\n"
                   f"{SCHEMA}\n\n{LEAF_RULES}")
    else:
        context = "The object is a rubric tree with the keys intention, static and dynamic."
    return _messages(_REPAIR_SYSTEM, _REPAIR_USER.substitute(
        query=query, context=context, errors="\n".join(f"- {e}" for e in errors),
        obj=_dump(obj)))


def baseline_messages(query: str) -> list[dict]:
    return [{"role": "user", "content": _BASELINE.substitute(
        example_query=EXAMPLE_QUERY, example_tree=_dump(webdevjudge_tree(EXAMPLE_TREE)),
        query=query)}]


def _universal_note(universal: list[dict]) -> str:
    lines = "\n".join(
        f"- {u['description']}" + (" (critical)" if u["critical"] else "") for u in universal)
    return ("Code adds these universal leaves to the static branch. Do not write them "
            "yourself. They count toward the leaf and critical limits:\n" + lines)


def _messages(system: str, user: str) -> list[dict]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
