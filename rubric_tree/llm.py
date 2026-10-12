"""OpenAI-compatible chat client that returns one JSON object per call.

Every attempt goes to the case's calls.jsonl: prompt, response, model,
temperature, usage and latency. A response without a JSON object is retried
up to PARSE_RETRIES times, with the temperature 0.1 higher each time
(as WebDevJudge does).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any

PARSE_RETRIES = 3
MAX_TOKENS = 16384
REQUEST_TIMEOUT_S = 600

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


class LLMError(RuntimeError):
    pass


def extract_json(text: str) -> dict:
    """The JSON object in a model response: the whole text, else the first
    fenced block, else the first bare object. Reasoning in <think> is ignored."""
    text = _THINK.sub("", text).strip()
    candidates = [text] + _FENCE.findall(text)
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("no JSON object in the response")


class LLM:
    """One endpoint, the models to use for each role, and a request limit."""

    def __init__(self, *, model: str, base_url: str = "", api_key: str = "",
                 draft_models: list[str] | None = None, critic_model: str = "",
                 concurrency: int = 8):
        self.model = model
        self.draft_models = list(draft_models or [])
        self.critic_model = critic_model or model
        self._base_url = base_url
        self._api_key = api_key
        self._client = None
        self._sem = asyncio.Semaphore(concurrency)
        # Sticky for the run: a gateway that rejects a parameter once rejects
        # it on every call.
        self._no_temperature = False
        self._no_json_mode = False

    @classmethod
    def from_env(cls, concurrency: int = 8) -> "LLM":
        env = {k: os.environ.get(k, "").strip() for k in
               ("RT_BASE_URL", "RT_API_KEY", "RT_MODEL", "RT_DRAFT_MODELS", "RT_CRITIC_MODEL")}
        if not env["RT_MODEL"] or not env["RT_API_KEY"]:
            raise SystemExit("set RT_MODEL and RT_API_KEY (see .env.example)")
        return cls(model=env["RT_MODEL"], base_url=env["RT_BASE_URL"],
                   api_key=env["RT_API_KEY"],
                   draft_models=[m.strip() for m in env["RT_DRAFT_MODELS"].split(",") if m.strip()],
                   critic_model=env["RT_CRITIC_MODEL"], concurrency=concurrency)

    async def chat_json(self, messages: list[dict], *, stage: str, model: str = "",
                        temperature: float = 0.0,
                        log_path: Path | None = None) -> tuple[dict, dict]:
        """(parsed object, summed usage of all attempts)."""
        model = model or self.model
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
        error = ""
        for attempt in range(1 + PARSE_RETRIES):
            t = round(temperature + 0.1 * attempt, 2)
            start = time.monotonic()
            async with self._sem:
                text, call_usage = await self._complete(
                    messages, model=model, temperature=t, stage=stage)
            usage["prompt_tokens"] += call_usage.get("prompt_tokens", 0)
            usage["completion_tokens"] += call_usage.get("completion_tokens", 0)
            usage["calls"] += 1
            try:
                obj, error = extract_json(text), ""
            except ValueError as e:
                obj, error = None, str(e)
            if log_path is not None:
                _append(log_path, {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "stage": stage,
                    "model": model, "temperature": t, "attempt": attempt + 1,
                    "latency_s": round(time.monotonic() - start, 2),
                    "usage": call_usage, "parse_error": error,
                    "messages": messages, "response": text})
            if obj is not None:
                return obj, usage
        raise LLMError(f"{stage}: no JSON object after {1 + PARSE_RETRIES} attempts ({error})")

    async def _complete(self, messages: list[dict], *, model: str, temperature: float,
                        stage: str) -> tuple[str, dict]:
        """One raw completion: (text, usage). Tests replace this method."""
        import openai

        if self._client is None:
            self._client = openai.AsyncOpenAI(
                api_key=self._api_key, base_url=self._base_url or None,
                timeout=REQUEST_TIMEOUT_S, max_retries=3)
        request: dict[str, Any] = {"model": model, "messages": messages,
                                   "max_tokens": MAX_TOKENS}
        if not self._no_temperature:
            request["temperature"] = temperature
        if not self._no_json_mode:
            request["response_format"] = {"type": "json_object"}
        while True:
            try:
                response = await self._client.chat.completions.create(**request)
                break
            except (openai.BadRequestError, openai.UnprocessableEntityError) as e:
                text = str(e).lower()
                if "temperature" in request and "temperature" in text:
                    self._no_temperature = True
                    request.pop("temperature")
                elif "response_format" in request and ("response_format" in text
                                                       or "json_object" in text):
                    self._no_json_mode = True
                    request.pop("response_format")
                else:
                    raise
        usage = response.usage
        return (response.choices[0].message.content or "",
                {"prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                 "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                 "finish_reason": response.choices[0].finish_reason})


def _append(path: Path, entry: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
