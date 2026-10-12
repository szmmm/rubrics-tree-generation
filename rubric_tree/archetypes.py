"""App archetypes, their default expectations, and the universal leaves.

The guidance is the simplest form of the MiniAppBench "domain-specific
instructions" and the RubricsTree router: stage 1 picks 1-3 archetype ids, and
the draft prompt gets the bullets of those archetypes. Leaves that come only
from this guidance get origin "archetype" and weight <= 3.

The universal leaves are fixed checks that code adds to every tree (RLCF
universal items; RCCA runtime gate). No LLM writes or changes them.
"""
from __future__ import annotations

ARCHETYPES: dict[str, dict] = {
    "game": {
        "summary": "a game, or a clone of a known game",
        "guidance": [
            "The core rules work correctly: legal moves, turn order, scoring.",
            "For a clone of a known game, the key mechanics, setting and "
            "story beats of the original are present (the judge checks them "
            "against the original).",
            "The game reaches a clear end state (win, lose or draw) and tells "
            "the player.",
            "The player can start a new game without reloading the page.",
            "The current state (whose turn, score, resources) is visible.",
        ],
    },
    "tracker": {
        "summary": "a long-term tracker, habit, check-in or record-keeping app",
        "guidance": [
            "Records persist after a page reload.",
            "The user can create, edit and delete a record.",
            "An empty state tells the user what to do first.",
            "Statistics or a summary view reflect the records the user "
            "entered, and change when the records change.",
            "A plan that spans days or weeks shows \"today\" correctly and "
            "advances.",
            "A check-in for a day is possible and stays visible afterwards.",
        ],
    },
    "guide": {
        "summary": "a guide, itinerary, buying guide or advice page",
        "guidance": [
            "The content is specific to the user's stated constraints "
            "(place, dates, budget, people), not generic.",
            "Recommendations name concrete options (places, products, "
            "dishes), not only categories.",
            "Numbers are consistent: budget items add up to the total; the "
            "number of days matches the trip length.",
            "Prices, opening hours and schedules are plausible for the "
            "user's dates; values that can change are labeled as estimates "
            "with a date or a source.",
            "Practical details that the user's context needs are present "
            "(for example child-friendly or elderly-friendly options).",
            "The user can find a section quickly (by day or by topic).",
        ],
    },
    "showcase": {
        "summary": "a showcase, fan, tribute or media page about a real "
                   "person, work or event",
        "guidance": [
            "Facts about the real person, work or event are correct "
            "(names, dates, places).",
            "Invented content (sample quotes, fan messages) is not shown as "
            "real facts or real quotes of named people.",
            "Images load, and an image shown as a real photo shows what it "
            "claims to show.",
            "Every section the user asked for has real content, not "
            "placeholder text.",
        ],
    },
    "news": {
        "summary": "news, a digest or other fresh information",
        "guidance": [
            "Each item shows a date, and the dates are recent relative to "
            "today.",
            "Items are real events, not invented headlines (the judge "
            "checks them).",
            "Each item links to a real source page.",
            "A summary agrees with the source it links to.",
            "The items cover the scope the user asked for (for example both "
            "industry and academia).",
        ],
    },
    "decision_tool": {
        "summary": "a decision, recommendation or analysis tool that takes "
                   "user inputs",
        "guidance": [
            "The tool accepts the inputs the user named.",
            "The result depends on the inputs: a changed input changes the "
            "result in a sensible direction.",
            "Each recommendation gives reasons that refer to the inputs.",
            "Missing or invalid input gives a clear message, not a crash or "
            "a silent wrong result.",
            "Data that the result depends on (scores, prices) is real, or "
            "labeled as a sample or estimate with a year or a source.",
        ],
    },
    "media_player": {
        "summary": "an ambient sound, music, podcast or other media player",
        "guidance": [
            "Audio plays when the user starts it, and stops when the user "
            "stops it.",
            "The user can switch between the offered sounds or tracks.",
            "The audio sources load; no track is silent or a broken link.",
            "When the user asked for a mood or style, the visual style "
            "matches it.",
        ],
    },
    "other": {
        "summary": "anything that does not fit the archetypes above",
        "guidance": [
            "The main flow that the user described works end to end.",
        ],
    },
}

ARCHETYPE_IDS = tuple(ARCHETYPES)

_LANGUAGE_NAMES = {"zh": "中文", "en": "英文"}


def guidance(archetype_ids: list[str]) -> str:
    """The guidance bullets for the given archetypes, as prompt text."""
    parts = []
    for aid in archetype_ids:
        bullets = "\n".join(f"- {b}" for b in ARCHETYPES[aid]["guidance"])
        parts.append(f"{aid} ({ARCHETYPES[aid]['summary']}):\n{bullets}")
    return "\n\n".join(parts)


def universal_leaves(spec: dict) -> list[dict]:
    """The fixed leaves that code adds to the static branch of every tree."""
    language = _LANGUAGE_NAMES.get(spec.get("ui_language", ""), "与用户提问一致的语言")
    leaves = [
        _leaf("页面正常加载，无白屏或阻断使用的报错", weight=5, critical=True),
        _leaf(f"界面主要文字使用{language}", weight=2),
    ]
    if spec.get("delivery") == "mobile_app":
        leaves.append(_leaf("在手机宽度（约 390px）下布局可用，无横向溢出", weight=3))
    return leaves


def _leaf(description: str, *, weight: int, critical: bool = False) -> dict:
    return {"description": description, "weight": weight, "critical": critical,
            "origin": "universal", "covers": [], "verify_by": "view",
            "children": None}
