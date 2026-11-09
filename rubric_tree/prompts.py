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

CRITICAL_BAR = (
    "Critical bar: a requirement or a leaf is critical only if failing it, by itself, "
    "badly hurts the user's experience or the user's view of the result. Test: think of "
    "an app that does everything else well but fails this one. If the user would call "
    "that app broken, wrong, or not what they asked for, it is critical. If the user "
    "would only find it weaker, less complete or less polished, it is not critical. A "
    "nice-to-have feature is never critical.")

SCHEMA = """\
## Rubric tree format

The tree has four branches. A branch root is {"description": "...", "children": [...]}.

- intention: the core goals. "Does this app do what the user wanted at all?"
- content: the information the app shows. Accuracy, completeness, fit to the user's context, internal consistency (sums, dates), freshness. An empty children list only if the query has no content needs (for example a pure chess game).
- static: visible structure and look on load. Required sections and elements, readable layout, mobile layout when the user said "APP", visual style when the user asked for one.
- dynamic: exactly two children, in this order: basic interactions, then complex interactions.
  - basic: single-step interactions (tap, type, select, play).
  - complex: multi-step flows and state changes (create -> reload -> still there; finish a game; switch person and see other data).

Every node below a branch root has these fields:
- description: for a group, a short group name; for a leaf, one yes/no statement.
- critical: true or false. Only a leaf can be critical. A critical leaf is a hard boundary: if it fails, the score of the whole app is 0, whatever the other leaves say. If no critical leaf fails, the score is the share of leaves that pass. Every leaf has the same weight, so the number of leaves that check a need is the weight of that need.
- children: a list of nodes for a group; null for a leaf.
A leaf also has:
- origin: "explicit" (stated in the query) | "implicit" (a must-be quality: inferred from the query's context or from what every product of this kind has) | "attractive" (a feature the user did not ask for but would value) | "archetype" (default expectation for this kind of app).
- covers: the spec requirement ids (R1, R2, ...) that the leaf checks. Required for explicit, implicit and attractive leaves.
- verify_by: "view" (visible on load or in the code) | "interaction" (needs user actions) | "fact" (needs external knowledge or a search to check). Every leaf under dynamic uses "interaction".
- note (optional): guidance for the judge: tolerance, accepted alternatives.

Do not write ids; code assigns them.
Size: 15-40 leaves in total, depending on how complex the query is. At most 4 levels below a branch root.
If the query implies an archetype expectation, write it as an implicit leaf with a covers id instead.
Every spec requirement is in the covers of at least one leaf.
Attractive leaves: check each attractive requirement with one leaf, origin "attractive", that covers only attractive requirements. No other leaf covers an attractive requirement. At most 4 attractive leaves per tree (code checks). An attractive leaf is never critical. Otherwise it is a normal leaf: same weight, same rules.
Write every description and note in the language of the query."""

LEAF_RULES = f"""\
## Leaf-writing rules

1. Atomic: one checkable fact per leaf. If a real app can pass one part of a leaf and fail another, split the leaf. No "和/并且" joining two checks.
2. Binary and observable: a judge answers yes or no from the app. Observable defects (overlapping or cut-off text, low contrast) are normal leaves. When design_focus is false, code adds one universal leaf for overall visual quality: do not write your own generic look leaf (Bad: "页面很美观"). When design_focus is true, write yes/no leaves for the look the user asked for, each with a note that tells the judge what to look at. Example: "页面整体呈现复古像素游戏风格", note "看字体、图标和边框是否为像素风格".
3. Self-contained: the leaf makes sense without reading the query.
4. Functional, not literal: describe the user-visible effect, not a label, layout, element type or library — unless the user named it. Bad: "有一个名为'今日任务'的卡片". Good: "打开应用即可看到当天要做的学习任务".
5. Feasible in the environment profile. Example for a frontend-only profile: do not require live flight prices; require prices labeled as estimates with a date or source.
6. Correct facts, but no uncertain facts in the leaf. When the app must show facts (the spec has knowledge_needs), write verify_by: "fact" leaves that check that the facts the user's goal depends on are correct (for example rules, prices, dates, names). If generator_confident is false, write a verify_by: "fact" leaf that states what the judge must check. Bad: "列出电影《X》". Good: "列出的电影在评测时确实在中国大陆院线近期上映". A leaf states what the judge checks, not your answer. When reputable sources differ (doses, temperatures, durations, frequencies, thresholds), the leaf checks that the app agrees with an authoritative source, not with your values. Bad: "泡脚水温约37–40℃、每次10–20分钟". Good: "手册给出的泡脚水温和时长与它引用的权威来源一致". Values in a note are examples, not the bar. Dates follow the spec: write the absolute dates that the spec resolved against time_frame.date, the user's today. Do not require a fact that became known after that date (for example the results of matches played later). Do not fail an app for showing such a fact when it is correct: a leaf about it accepts both what was known at that date (待定, placeholders) and the correct later fact. Before you write a number that can be computed from data in the query into a leaf or a note, compute it again yourself. Do not copy it from the spec without a check. Check its units and its order of magnitude. If you cannot get the same result again, do not write the number: tell the judge how to compute it.
7. Positive polarity: pass = good. Write pitfalls as positive leaves. Example: "预算各项之和与总预算一致".
8. No double counting. Every leaf has the same weight, so a check that two leaves make counts two times. No two leaves may be duplicates, in the same branch or in different branches, intention included. Two leaves are duplicates when they check the same thing, or when a judge who tests a real app would almost always give both the same answer. Keep one of them. Common cases:
   - An intention leaf and a detailed leaf check the same goal (for example "用户能切换历史会话" and "点击左侧另一个会话，主区域显示该会话的消息"). Keep the leaf in intention, with the more exact wording and note of the two, and remove the other.
   - One leaf checks that a control or section is there, and another leaf uses that control or reads that section (for example "每场比赛旁有勾选框" and "点击勾选框后该场比赛被标记为已选"). Keep the leaf that uses it.
   - One feature split into steps that pass or fail together (for example a music player that can play, pause and resume: keep one leaf).
   - The same check again in a later flow, with nothing new to check.
A single step and a longer flow that contains it are not duplicates when the flow checks something new that can fail after the step works (for example the data is still there after a reload).
9. Gate by the critical bar. A failed critical leaf sets the whole score to 0. {CRITICAL_BAR} Mark a leaf critical only if it meets this bar by itself and covers at least one critical requirement. When several leaves cover the same critical requirement, mark only the leaf that checks its core. A judge must be able to decide a critical leaf without taste: never mark a look or style leaf critical. A critical leaf checks that the app does or answers what the user asked, not that it gives your answer: it states no number, date, name, rule or recommendation that is not in the query. The user's today (spec.time_frame.date) is an estimate, so a leaf whose verdict depends on it (for example "不推荐已经结束的场次" or "报名截止日还没过") is critical only if the query itself states the date. There is no fixed number: every leaf that meets the bar is critical, and no other. Never on a branch root."""

ISSUE_TYPES = """\
- missing: a spec requirement has no adequate leaf, a core flow is not tested end to end, or the tree checks only the core function and misses a must-be quality that every competent product of this kind has and that the main flows need (fix: add it as an archetype leaf)
- not_atomic: the leaf checks two things
- subjective: a look leaf without a note that tells the judge what to look at, or a generic look leaf that repeats the universal one
- over_specific: the leaf demands one implementation where others serve the user equally
- too_broad: the leaf is too vague to fail
- ungrounded: the leaf demands a feature with no basis in the query, the archetype or an attractive requirement (gold-plating). An attractive leaf that covers an attractive requirement is grounded: do not ask to remove it. If its wording is generic, names a mechanism instead of a user-visible result, or goes against a stated wish, give a fix that rewrites it;
- infeasible: the leaf cannot pass in the environment profile, it requires a fact that was not known at the user's today (spec.time_frame.date), or it fails an app that shows such a fact correctly
- hardcoded_fact: a leaf or a note states a fact as the expected answer, and the fact is wrong or uncertain. Check every number, name, date and rule yourself; generator_confident in the spec is not proof. Also: a leaf makes one source's values the bar where reputable sources differ (rule 6), or a critical leaf states a value that is not in the query (rule 9)
- duplicate: two leaves are duplicates by leaf rule 8, in the same branch or in different branches. Give the leaf to remove in leaf_id and the leaf to keep in fix
- contradiction: two leaves, or a leaf and a note, disagree: one requires something that another calls optional or lets pass without it
- balance: a critical flag fails the critical bar (a leaf is critical but fails the test, or a leaf meets the test but is not critical), a critical leaf is a look or style leaf, or look leaves outnumber function leaves when design_focus is false
- wrong_branch: the leaf is in the wrong branch, or verify_by is wrong"""

SPEC_RULES = f"""\
- There are three types of requirement. They follow the Kano model of product quality: what the user asked for, what the user takes for granted, and what the user did not expect but values.
- Explicit requirement = stated in the query, or follows directly from words in the query. evidence_quote is those words and must be an exact substring of the query (code checks this). Examples: "高血糖父母" means low-sugar dishes with a low glycemic index; "小孩两岁半" means child-friendly travel; "长期用" means the data persists.
- Implicit requirement (must-be quality) = a need that no words in the query state, but that a typical user with this request takes for granted. If the app does not meet it, the user is let down; if it does, the user does not notice. It comes from one of two sources:
  - this user's context. Example: an app to manage the family fridge is used every day, so the records persist.
  - what every competent product of this kind has today. Examples: an editor can undo a change; the user can edit and delete what they added; a delete asks for confirmation or can be undone; invalid input gets a clear message instead of a wrong result.
  Write the must-be qualities that the main flows of this app need, not every one that you can think of. The rationale cites the context or the kind of product.
- Attractive requirement (attractive quality) = a feature that no words in the query state and that the user would not miss, but would notice and value. It serves this user's goal, or the next thing the user does with the result, and the rationale names the words of the query that it serves. Example: the user writes a daily news digest to post in a WeChat group, so the app copies the digest in one click, ready to paste into WeChat. Rules:
  - 0 to 4 per query (code checks). Fewer is normal: 0 or 1 for a simple or narrow request. Write none that goes against a stated wish, for example a request to keep the app simple or to leave out other features ("别的都不用").
  - Never critical: a user is not let down by a feature they did not expect.
  - Specific to this query. Bad: a feature you could add to any app ("有深色模式", "有动画效果"). A quality that users of this kind of product take for granted today is implicit, not attractive.
  - A user-visible result, not a mechanism or a library. It is feasible in the environment profile.
  - When there are more candidates than the cap, keep the ones that most users with this request would value most.
- The bar for explicit and implicit requirements: if the app does not meet it, the user's goal fails or the user is let down. A feature that is only nice to have is not an explicit or implicit requirement; it can be attractive.
- Make each requirement one need: no "or" lists, no "最好" or "ideally".
- A requirement states the need, not the answer: no values that you supply (numbers, doses, durations, dates, names, rules) unless the query states them. Write the facts that you know into knowledge_needs.
- critical: true or false. Always false for an attractive requirement. {CRITICAL_BAR}
- Do not write requirements for the environment profile, or for what code checks in every app: the page loads, the UI language, the layout at mobile width.
- Write text and rationale in the language of the query.
- time_frame: when the user wrote the query, and the period it is about.
  - date: the user's today, the day the user wrote the query, not the time of the events in it. It is as_of, unless the query's own words show that the user wrote at another time: an event, a year or a season that does not fit as_of. Work it out from the relative words. Example: as_of is 2026-10-23 and the query says "明年巴黎奥运会". The Paris Olympics were in 2024 and "明年" is the next year, so the user wrote in 2023: the date is "2023", not "2024". The query can also show it with no calendar word: the user plans for an event, or asks about it as still to come, but the event ended before as_of. Example: as_of is 2026-10-23 and the query says "今年想去现场看温网". Wimbledon 2026 was from 2026-06-29 to 2026-07-12, and the user plans to go, so the user wrote before 2026-06-29: the date is "2026", and the rationale says "before 2026-06-29". Do this check for every dated event in the query: matches, festivals, exams, holidays, sales and seasons. Keep as_of only if no event in the query ended before as_of while the user still plans for it. Write such a date as "YYYY", "YYYY-MM" or "YYYY-MM-DD", as exact as the query shows, with evidence_quote (an exact substring of the query, checked by code) and a rationale.
  - refers_to: only if the query is about a dated event or period: that period in absolute dates. Example: "2024年7-8月，巴黎奥运会".
  When the date is as_of, write {{"date": as_of}}, plus refers_to if the query has one.
- Resolve calendar words ("今天", "明天", "今年", "明年", "下周", "国庆节", "这届") against time_frame.date into absolute dates in text and rationale, as exact as that date allows, and keep the word: "2024年巴黎奥运会（明年）". An evidence_quote still copies the query exactly. Keep absolute dates from the query as they are.
- Keep freshness words relative ("最近", "最新", "近期"): the judge checks them on the evaluation date, because the app must be current when it is used.
- knowledge_needs: facts the app must show and a judge must check (prices, schedules, names, events, the rules of a known game). Mark generator_confident: false for facts you cannot state with confidence at time_frame.date. When a fact can be computed from data in the query (for example a sum, a unit conversion, a time-zone conversion, or the solution of given equations), compute it, then compute it again by a different path and compare the two results. Check the units and the order of magnitude. If the results do not agree, mark generator_confident: false.
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
  "time_frame": {"date": "<as_of>"} | {"date": "2023", "evidence_quote": "...", "rationale": "...", "refers_to": "..."},
  "requirements": [
    {"id": "R1", "type": "explicit", "text": "...", "evidence_quote": "...", "critical": true},
    {"id": "R2", "type": "implicit", "text": "...", "rationale": "...", "critical": false},
    {"id": "R3", "type": "attractive", "text": "...", "rationale": "...", "critical": false}
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
    "time_frame": {"date": "2026-10-12"},
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
        {"id": "R7", "type": "attractive", "text": "推荐菜时优先用上快过期的食材",
         "rationale": "用户既要“快过期的要提醒我”，又要“根据现有食材推荐几道菜”；推荐时先消耗快过期的食材能少浪费，用户没有要求，但会看重",
         "critical": False},
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
        _leaf("用户填写食材名称和过期日期后，可以把食材加入清单", "explicit",
              ["R1", "R2"], "interaction", critical=True),
        _leaf("加入一种明天过期的食材后，打开应用的首屏就能看到它快过期的提醒", "explicit", ["R3"], "interaction",
              note="横幅、角标、标签、置顶都可以；浏览器通知不是必须的", critical=True),
        _leaf("用户可以发起推荐，并看到至少一道推荐的菜", "explicit", ["R4"],
              "interaction"),
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
    ]},
    "dynamic": {"description": "交互", "children": [
        _group("基础交互", [
            _leaf("用户可以把吃完或扔掉的食材从清单中移除", "implicit", ["R6"],
                  "interaction", note="删除或标记为已用完都可以"),
            _leaf("用户可以修改已有食材的过期日期", "archetype", [], "interaction"),
        ]),
        _group("复杂交互", [
            _leaf("过期日期在一个月以后的食材不会被提醒为快过期", "explicit", ["R3"],
                  "interaction", note="“快过期”的天数由应用决定，1 到 7 天都合理"),
            _leaf("加入食材后刷新页面，食材清单仍然保留", "implicit", ["R5"],
                  "interaction", note="localStorage 或后端保存都可以", critical=True),
            _leaf("清单里的食材变化后，再次推荐的菜随之变化", "explicit", ["R4"],
                  "interaction"),
            _leaf("清单里有一种明天过期的食材时，推荐的菜中至少有一道用到它", "attractive", ["R7"],
                  "interaction", note="测试时选一种常用于家常菜的食材，例如鸡蛋或西红柿"),
        ]),
    ]},
}

EXAMPLE_DRAFT = {"tree": EXAMPLE_TREE}

# ── stage prompts ────────────────────────────────────────────────────────────

_SPEC_SYSTEM = Template("""\
You analyze one request for a web app before anyone writes a rubric for it. Find what the user asked for (explicit requirements), what a typical user with this request takes for granted (implicit requirements), what this user did not ask for but would value (attractive requirements), and which facts a judge must check. Return one JSON object only.

Rules:
$rules

Archetypes:
$archetypes

Output format (JSON):
$format""")

_SPEC_USER = Template("""\
as_of (the user's today, unless the query shows another time): $as_of
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
The user's today (spec.time_frame.date): $today
Environment profile: $env

User query:
$query

Spec (query analysis):
$spec

Default expectations for this kind of app. Use the ones that fit this query; mark them origin "archetype" unless the query implies them:
$guidance

$universal

Return JSON:
{"tree": {"intention": {...}, "content": {...}, "static": {...}, "dynamic": {...}}}""")

_MERGE_SYSTEM = Template("""\
You merge $k draft rubric trees for the same web-app request into one tree. Return one JSON object only.

Task:
- Combine the drafts into one tree: keep every check that appears in any draft. Do not drop a check only to make the tree smaller.
- Write duplicates (rule 8) as one leaf with the clearest wording, also when the drafts word or place them differently.
- If more than 40 leaves remain, keep the checks with the highest support.
- Set each critical flag by the critical bar (rule 9). Do not keep a flag only because a draft set it.
- Keep at most 4 levels below a branch root.
- For each leaf, add "support": the number of drafts (1-$k) that contain an equivalent leaf.

$schema

$leaf_rules""")

_MERGE_USER = Template("""\
The user's today (spec.time_frame.date): $today
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

Be strict. Check every leaf against every rule, then check the leaves against each other:
1. For each spec requirement, find all the leaves that cover it, in all four branches, intention included. Report each pair of leaves that are duplicates by rule 8.
2. Compare each leaf and note with the others. Report each contradiction.
3. Check each number, name, date and rule in the leaves and notes yourself. Compute again each number that can be computed from data in the query, and check its units and order of magnitude. Report a wrong one as hardcoded_fact.
4. Apply the critical bar to every leaf, critical or not.
5. Check that the leaves cover the must-be qualities of this kind of product that the main flows need, not only the core function.
Report every problem that you find, not only the first few.

severity: "blocking" if the issue changes a verdict or the score in a way the user would not accept: a missing core check, a check that a good app can fail, a wrong gate, looks that outweigh function, a duplicate, a contradiction, a wrong fact. "minor" if a judge would still read and score the leaf correctly.

Leaves with origin "universal" are fixed by code. Do not report them, except as the other half of a duplicate.
"support" on a leaf is the number of independent drafts that had it.

The tree must follow these rules:

$schema

$leaf_rules

Return JSON: {"issues": [{"leaf_id": "S.2" or null for a missing leaf, "type": "...", "severity": "blocking" | "minor", "fix": "what to change"}]}
Return an empty issues list only if you checked every leaf and found no problem.""")

_CRITIC_USER = Template("""\
The user's today (spec.time_frame.date): $today
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
The user's today (spec.time_frame.date): $today
Environment profile: $env

User query:
$query

Spec:
$spec

Issues:
$issues

Current tree:
$tree

Return the whole tree with all four branches, also the branches that no issue mentions.
Return JSON: {"tree": {"intention": {...}, "content": {...}, "static": {...}, "dynamic": {...}}}""")

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


def draft_messages(query: str, today: str, env_profile: str, spec: dict,
                   guidance: str, universal: list[dict]) -> list[dict]:
    return _messages(
        _DRAFT_SYSTEM.substitute(
            schema=SCHEMA, leaf_rules=LEAF_RULES, example_query=EXAMPLE_QUERY,
            example_spec=_dump(EXAMPLE_SPEC), example_draft=_dump(EXAMPLE_DRAFT)),
        _DRAFT_USER.substitute(
            today=today, env=ENV_PROFILES[env_profile], query=query, spec=_dump(spec),
            guidance=guidance, universal=_universal_note(universal)))


def merge_messages(query: str, today: str, env_profile: str, spec: dict,
                   drafts: list[dict], universal: list[dict]) -> list[dict]:
    blocks = "\n\n".join(f"Draft {i}:\n{_dump(d)}" for i, d in enumerate(drafts, 1))
    return _messages(
        _MERGE_SYSTEM.substitute(k=len(drafts), schema=SCHEMA, leaf_rules=LEAF_RULES),
        _MERGE_USER.substitute(
            today=today, env=ENV_PROFILES[env_profile], query=query, spec=_dump(spec),
            universal=_universal_note(universal), drafts=blocks))


def critic_messages(query: str, today: str, env_profile: str, spec: dict,
                    tree: dict) -> list[dict]:
    return _messages(
        _CRITIC_SYSTEM.substitute(issue_types=ISSUE_TYPES, schema=SCHEMA, leaf_rules=LEAF_RULES),
        _CRITIC_USER.substitute(
            today=today, env=ENV_PROFILES[env_profile], query=query, spec=_dump(spec),
            tree=_dump(tree)))


def revise_messages(query: str, today: str, env_profile: str, spec: dict,
                    tree: dict, issues: list) -> list[dict]:
    return _messages(
        _REVISE_SYSTEM.substitute(schema=SCHEMA, leaf_rules=LEAF_RULES),
        _REVISE_USER.substitute(
            today=today, env=ENV_PROFILES[env_profile], query=query, spec=_dump(spec),
            issues=_dump(issues), tree=_dump(tree)))


def repair_messages(obj, errors: list[str], *, query: str, kind: str,
                    spec: dict | None = None,
                    universal: list[dict] | None = None) -> list[dict]:
    """kind: "spec" (stage-1 output), "tree" ({tree}) or
    "baseline" (a WebDevJudge tree)."""
    if kind == "spec":
        context = (f"The object is a query analysis. Rules:\n{SPEC_RULES}\n\n"
                   f"Format:\n{SPEC_FORMAT}")
    elif kind == "tree":
        context = (f"The object is a rubric tree. Spec (read only):\n{_dump(spec)}\n\n"
                   f"{SCHEMA}\n\n{LEAF_RULES}\n\n{_universal_note(universal or [])}\n"
                   "Code puts them back exactly as listed after your fix, so fix the errors "
                   "by changing the other leaves only.\n"
                   'Return JSON: {"tree": {"intention": {...}, "content": {...}, '
                   '"static": {...}, "dynamic": {...}}}')
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
            "yourself. They count toward the leaf limits:\n"
            + lines)


def _messages(system: str, user: str) -> list[dict]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
