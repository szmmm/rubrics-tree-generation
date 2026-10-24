"""OpenAI-compatible chat client that returns one JSON object per call.

Every attempt goes to the case's calls.jsonl: prompt, response, model,
temperature, usage and latency. A response without a JSON object is retried
up to PARSE_RETRIES times, with a new seed. A response cut off at max_tokens (MAX_TOKENS, or
RT_MAX_TOKENS) counts as one without a JSON object: a part of it can parse,
but it is not the full answer. So does one that fails the caller's check.
Every call samples at TEMPERATURE 1.0 and TOP_P 0.95, the sampling DeepSeek
recommends for thinking. At temperature 0, DeepSeek-V4 thinking often repeats
the same lines until max_tokens (2026-10-24).
Every attempt sends its own random seed, for the endpoints that use it
(SGLang only with --enable-deterministic-inference).
Responses are streamed, because a gateway can end a request that streams
nothing (PAI-EAS: "stream timeout" after about 180 s).
Every call asks for thinking at REASONING_EFFORT ("high"); RT_REASONING_EFFORT
sets another level, or "off" to send neither parameter. DeepSeek-V4 on SGLang
needs both: without chat_template_kwargs.thinking it does not think at all.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Callable

PARSE_RETRIES = 3
MAX_TOKENS = 131072        # reasoning models spend most of it before the answer
REQUEST_TIMEOUT_S = 1800
REASONING_EFFORT = "high"  # DeepSeek-V4: low | high | max
TEMPERATURE = 1.0
TOP_P = 0.95

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
                 concurrency: int = 8, reasoning_effort: str = REASONING_EFFORT,
                 max_tokens: int = MAX_TOKENS):
        self.model = model
        self.draft_models = list(draft_models or [])
        self.critic_model = critic_model or model
        self.reasoning_effort = "" if reasoning_effort == "off" else reasoning_effort
        self.max_tokens = max_tokens
        self._base_url = base_url
        self._api_key = api_key
        self._client = None
        self._sem = asyncio.Semaphore(concurrency)
        # Sticky for the run: a gateway that rejects a parameter once rejects
        # it on every call.
        self._no_temperature = False
        self._no_json_mode = False
        self._no_seed = False
        self._no_reasoning = False

    @classmethod
    def from_env(cls, concurrency: int = 8) -> "LLM":
        env = {k: os.environ.get(k, "").strip() for k in
               ("RT_BASE_URL", "RT_API_KEY", "RT_MODEL", "RT_DRAFT_MODELS", "RT_CRITIC_MODEL",
                "RT_REASONING_EFFORT", "RT_MAX_TOKENS")}
        if not env["RT_MODEL"] or not env["RT_API_KEY"]:
            raise SystemExit("set RT_MODEL and RT_API_KEY (see .env.example)")
        max_tokens = MAX_TOKENS
        if env["RT_MAX_TOKENS"]:
            if not env["RT_MAX_TOKENS"].isdigit() or int(env["RT_MAX_TOKENS"]) < 1:
                raise SystemExit(f"RT_MAX_TOKENS must be a positive integer, not {env['RT_MAX_TOKENS']!r}")
            max_tokens = int(env["RT_MAX_TOKENS"])
        return cls(model=env["RT_MODEL"], base_url=env["RT_BASE_URL"],
                   api_key=env["RT_API_KEY"],
                   draft_models=[m.strip() for m in env["RT_DRAFT_MODELS"].split(",") if m.strip()],
                   critic_model=env["RT_CRITIC_MODEL"], concurrency=concurrency,
                   reasoning_effort=env["RT_REASONING_EFFORT"] or REASONING_EFFORT,
                   max_tokens=max_tokens)

    async def chat_json(self, messages: list[dict], *, stage: str, model: str = "",
                        temperature: float = TEMPERATURE,
                        check: Callable[[dict], str] | None = None,
                        log_path: Path | None = None) -> tuple[dict, dict]:
        """(parsed object, summed usage of all attempts). check returns an
        error for a parsed object that is not usable, or ""."""
        model = model or self.model
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
        error = ""
        for attempt in range(1 + PARSE_RETRIES):
            seed = random.randrange(2**31)
            start = time.monotonic()
            async with self._sem:
                text, call_usage = await self._complete(
                    messages, model=model, temperature=temperature, seed=seed, stage=stage)
            usage["prompt_tokens"] += call_usage.get("prompt_tokens", 0)
            usage["completion_tokens"] += call_usage.get("completion_tokens", 0)
            usage["calls"] += 1
            if call_usage.get("finish_reason") == "length":
                obj, error = None, f"response cut off at max_tokens ({self.max_tokens})"
            else:
                try:
                    obj, error = extract_json(text), ""
                except ValueError as e:
                    obj, error = None, str(e)
                if obj is not None and check is not None:
                    error = check(obj)
                    obj = None if error else obj
            if log_path is not None:
                _append(log_path, {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "stage": stage,
                    "model": model, "temperature": temperature,
                    "top_p": None if self._no_temperature else TOP_P,
                    "seed": seed, "attempt": attempt + 1,
                    "reasoning_effort": None if self._no_reasoning else (self.reasoning_effort or None),
                    "latency_s": round(time.monotonic() - start, 2),
                    "usage": call_usage, "parse_error": error,
                    "messages": messages, "response": text})
            if obj is not None:
                return obj, usage
        raise LLMError(f"{stage}: no JSON object after {1 + PARSE_RETRIES} attempts ({error})")

    async def _complete(self, messages: list[dict], *, model: str, temperature: float,
                        seed: int, stage: str) -> tuple[str, dict]:
        """One raw completion, streamed: (text, usage). Tests replace this method."""
        import openai

        if self._client is None:
            self._client = openai.AsyncOpenAI(
                api_key=self._api_key, base_url=self._base_url or None,
                timeout=REQUEST_TIMEOUT_S, max_retries=3)
        request: dict[str, Any] = {"model": model, "messages": messages,
                                   "max_tokens": self.max_tokens, "stream": True,
                                   "stream_options": {"include_usage": True}}
        if not self._no_temperature:
            request["temperature"] = temperature
            request["top_p"] = TOP_P
        if not self._no_json_mode:
            request["response_format"] = {"type": "json_object"}
        if not self._no_seed:
            request["seed"] = seed
        if self.reasoning_effort and not self._no_reasoning:
            request["reasoning_effort"] = self.reasoning_effort
            request["extra_body"] = {"chat_template_kwargs": {"thinking": True}}
        while True:
            try:
                stream = await self._client.chat.completions.create(**request)
                break
            except (openai.BadRequestError, openai.UnprocessableEntityError) as e:
                text = str(e).lower()
                if "temperature" in request and ("temperature" in text or "top_p" in text):
                    self._no_temperature = True
                    request.pop("temperature")
                    request.pop("top_p")
                elif "response_format" in request and ("response_format" in text
                                                       or "json_object" in text):
                    self._no_json_mode = True
                    request.pop("response_format")
                elif "seed" in request and "seed" in text:
                    self._no_seed = True
                    request.pop("seed")
                elif "reasoning_effort" in request and ("reasoning_effort" in text
                                                        or "chat_template_kwargs" in text):
                    self._no_reasoning = True
                    request.pop("reasoning_effort")
                    request.pop("extra_body")
                else:
                    raise
        parts, finish_reason, usage = [], None, None
        async for chunk in stream:
            if chunk.choices:
                parts.append(chunk.choices[0].delta.content or "")
                finish_reason = chunk.choices[0].finish_reason or finish_reason
            usage = chunk.usage or usage
        return ("".join(parts),
                {"prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                 "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                 "finish_reason": finish_reason})


def _append(path: Path, entry: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
