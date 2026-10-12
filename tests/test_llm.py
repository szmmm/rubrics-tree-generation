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


def test_bad_json_then_good_json_succeeds_after_retry(tmp_path):
    llm = FakeLLM({"spec": ["not json at all", '{"ok": true}']})
    log = tmp_path / "calls.jsonl"
    obj, usage = asyncio.run(llm.chat_json([{"role": "user", "content": "x"}], stage="spec",
                                           temperature=0.0, log_path=log))
    assert obj == {"ok": True}
    assert [c["temperature"] for c in llm.calls] == [0.0, 0.1]
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
        message = type("M", (), {"content": '{"ok": 1}'})
        choice = type("C", (), {"message": message, "finish_reason": "stop"})
        usage = type("U", (), {"prompt_tokens": 7, "completion_tokens": 3})
        return type("R", (), {"choices": [choice], "usage": usage})


def test_rejected_parameters_are_dropped_for_the_rest_of_the_run():
    llm = LLM(model="m", api_key="k")
    completions = _Completions()
    llm._client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})})
    obj, usage = asyncio.run(llm.chat_json([], stage="spec"))
    assert obj == {"ok": 1} and usage["prompt_tokens"] == 7
    assert len(completions.requests) == 3
    asyncio.run(llm.chat_json([], stage="spec"))
    assert len(completions.requests) == 4     # no rejected parameter is sent again
    assert "temperature" not in completions.requests[-1]
    assert "response_format" not in completions.requests[-1]
