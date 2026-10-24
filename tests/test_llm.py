import asyncio
import json

import openai
import pytest

from fakes import FakeLLM
from rubric_tree.llm import LLM, LLMError, extract_json


@pytest.mark.parametrize("text", [
    '{"a": 1}',
    'Here it is:\n```json\n{"a": 1}\n```\nDone.',
    '<think>maybe {"a": 0}?</think>\n{"a": 1}',
    'The answer is {"a": 1} and nothing else.',
])
def test_extract_json(text):
    assert extract_json(text) == {"a": 1}


@pytest.mark.parametrize("text", ["no json here", "[1, 2]", '{"a": '])
def test_extract_json_fails_without_an_object(text):
    with pytest.raises(ValueError):
        extract_json(text)


def test_an_object_that_fails_the_check_is_retried(tmp_path):
    llm = FakeLLM({"merge": ['{"tree": {"description": "x"}}', '{"tree": {"ok": 1}}']})
    log = tmp_path / "calls.jsonl"
    obj, usage = asyncio.run(llm.chat_json(
        [], stage="merge", log_path=log,
        check=lambda o: "" if "ok" in o["tree"] else "wrong shape"))
    assert obj == {"tree": {"ok": 1}} and usage["calls"] == 2
    assert [json.loads(line)["parse_error"] for line in log.read_text().splitlines()] ==         ["wrong shape", ""]


def test_bad_json_then_good_json_succeeds_after_retry(tmp_path):
    llm = FakeLLM({"spec": ["not json at all", '{"ok": true}']})
    log = tmp_path / "calls.jsonl"
    obj, usage = asyncio.run(llm.chat_json([{"role": "user", "content": "x"}], stage="spec",
                                           log_path=log))
    assert obj == {"ok": True}
    assert [c["temperature"] for c in llm.calls] == [1.0, 1.0]
    assert llm.calls[0]["seed"] != llm.calls[1]["seed"]
    assert usage == {"prompt_tokens": 200, "completion_tokens": 20, "calls": 2}
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert [e["parse_error"] != "" for e in entries] == [True, False]
    assert entries[0]["usage"] == {"prompt_tokens": 100, "completion_tokens": 10}
    assert entries[1]["response"] == '{"ok": true}' and entries[1]["stage"] == "spec"


def test_gives_up_after_the_parse_retries():
    llm = FakeLLM({"spec": ["still not json"]})
    with pytest.raises(LLMError, match="after 4 attempts"):
        asyncio.run(llm.chat_json([], stage="spec"))
    assert len(llm.calls) == 4


class _CutOffOnce(FakeLLM):
    """The first response stops at max_tokens."""

    async def _complete(self, messages, *, model, temperature, seed, stage):
        text, usage = await super()._complete(messages, model=model, temperature=temperature,
                                              seed=seed, stage=stage)
        return text, {**usage, "finish_reason": "length" if len(self.calls) == 1 else "stop"}


def test_a_response_cut_off_at_max_tokens_is_retried():
    # The outer object is cut off. Its complete inner object is not the answer.
    llm = _CutOffOnce({"draft": ['{"weights": {"a": 1}, "tree": {', '{"ok": true}']})
    obj, usage = asyncio.run(llm.chat_json([], stage="draft"))
    assert obj == {"ok": True} and usage["calls"] == 2


class _Rejected(openai.BadRequestError):
    """A 400 without an HTTP response object (the SDK's HTTP library varies)."""

    def __init__(self, message):
        Exception.__init__(self, message)


class _Completions:
    """Rejects temperature and response_format once each, like some gateways."""

    def __init__(self):
        self.requests = []

    async def create(self, **request):
        self.requests.append(dict(request))
        for name in ("temperature", "response_format"):
            if name in request:
                raise _Rejected(f"Unsupported parameter: '{name}'")
        return _stream(['{"ok"', ': 1}'])


async def _stream(pieces):
    """Chunks as the SDK streams them: content deltas, then usage alone."""
    for i, piece in enumerate(pieces, 1):
        delta = type("D", (), {"content": piece})
        choice = type("C", (), {"delta": delta,
                                "finish_reason": "stop" if i == len(pieces) else None})
        yield type("Chunk", (), {"choices": [choice], "usage": None})
    usage = type("U", (), {"prompt_tokens": 7, "completion_tokens": 3})
    yield type("Chunk", (), {"choices": [], "usage": usage})


def test_rejected_parameters_are_dropped_for_the_rest_of_the_run():
    llm = LLM(model="m", api_key="k")
    completions = _Completions()
    llm._client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})})
    obj, usage = asyncio.run(llm.chat_json([], stage="spec"))
    assert obj == {"ok": 1} and usage["prompt_tokens"] == 7
    assert len(completions.requests) == 3
    assert completions.requests[-1]["stream"] is True
    asyncio.run(llm.chat_json([], stage="spec"))
    assert len(completions.requests) == 4     # no rejected parameter is sent again
    assert "temperature" not in completions.requests[-1]
    assert "top_p" not in completions.requests[-1]
    assert "response_format" not in completions.requests[-1]


class _Recorder:
    """Accepts every request, or rejects the ones that carry `reject` once."""

    def __init__(self, reject: str = ""):
        self.requests, self.reject = [], reject

    async def create(self, **request):
        self.requests.append(dict(request))
        if self.reject and self.reject in request:
            raise _Rejected(f"Unsupported parameter: '{self.reject}'")
        return _stream(['{"ok": 1}'])


def _llm_with(completions, **kwargs):
    llm = LLM(model="m", api_key="k", **kwargs)
    llm._client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})})
    return llm


def test_thinking_at_high_effort_is_the_default(tmp_path):
    completions = _Recorder()
    log = tmp_path / "calls.jsonl"
    asyncio.run(_llm_with(completions).chat_json([], stage="spec", log_path=log))
    request = completions.requests[-1]
    assert request["reasoning_effort"] == "high"
    assert request["extra_body"] == {"chat_template_kwargs": {"thinking": True}}
    assert json.loads(log.read_text())["reasoning_effort"] == "high"


def test_every_call_samples_at_temperature_1_and_top_p_095(tmp_path):
    completions = _Recorder()
    log = tmp_path / "calls.jsonl"
    asyncio.run(_llm_with(completions).chat_json([], stage="spec", log_path=log))
    request = completions.requests[-1]
    assert (request["temperature"], request["top_p"]) == (1.0, 0.95)
    entry = json.loads(log.read_text())
    assert (entry["temperature"], entry["top_p"]) == (1.0, 0.95)


@pytest.mark.parametrize("value, effort", [("", "high"), ("max", "max"), ("off", None)])
def test_rt_reasoning_effort_sets_the_level(monkeypatch, value, effort):
    monkeypatch.setenv("RT_MODEL", "m")
    monkeypatch.setenv("RT_API_KEY", "k")
    monkeypatch.setenv("RT_REASONING_EFFORT", value)
    llm = LLM.from_env()
    completions = _Recorder()
    llm._client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})})
    asyncio.run(llm.chat_json([], stage="spec"))
    assert completions.requests[-1].get("reasoning_effort") == effort
    assert ("extra_body" in completions.requests[-1]) == (effort is not None)


@pytest.mark.parametrize("value, max_tokens", [("", 131072), ("32768", 32768)])
def test_rt_max_tokens_sets_the_cap(monkeypatch, value, max_tokens):
    monkeypatch.setenv("RT_MODEL", "m")
    monkeypatch.setenv("RT_API_KEY", "k")
    monkeypatch.setenv("RT_MAX_TOKENS", value)
    llm = LLM.from_env()
    completions = _Recorder()
    llm._client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})})
    asyncio.run(llm.chat_json([], stage="spec"))
    assert completions.requests[-1]["max_tokens"] == max_tokens


@pytest.mark.parametrize("value", ["lots", "0", "-5", "1.5"])
def test_rt_max_tokens_must_be_a_positive_integer(monkeypatch, value):
    monkeypatch.setenv("RT_MODEL", "m")
    monkeypatch.setenv("RT_API_KEY", "k")
    monkeypatch.setenv("RT_MAX_TOKENS", value)
    with pytest.raises(SystemExit, match="RT_MAX_TOKENS"):
        LLM.from_env()


class _AlwaysCutOff(FakeLLM):
    async def _complete(self, messages, *, model, temperature, seed, stage):
        text, usage = await super()._complete(messages, model=model, temperature=temperature,
                                              seed=seed, stage=stage)
        return text, {**usage, "finish_reason": "length"}


def test_the_cut_off_error_names_the_cap_in_use():
    llm = _AlwaysCutOff({"draft": ['{"a": ']}, max_tokens=1000)
    with pytest.raises(LLMError, match=r"max_tokens \(1000\)"):
        asyncio.run(llm.chat_json([], stage="draft"))


def test_a_rejected_reasoning_effort_turns_thinking_off_for_the_run():
    completions = _Recorder(reject="reasoning_effort")
    llm = _llm_with(completions)
    asyncio.run(llm.chat_json([], stage="spec"))
    asyncio.run(llm.chat_json([], stage="spec"))
    assert len(completions.requests) == 3
    assert "reasoning_effort" not in completions.requests[-1]
    assert "extra_body" not in completions.requests[-1]
