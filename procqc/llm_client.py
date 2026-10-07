"""Thin Fuelix client (OpenAI-compatible) for JSON-returning calls.

One place that knows how to talk to the provider, so every other module is
provider-agnostic:

* ``response_format={"type": "json_schema", ...}`` when the model/proxy supports it,
  falling back to ``{"type": "json_object"}`` and finally to prompt-instructed JSON
  with a tolerant extractor.
* Retries with exponential backoff on rate limits / 5xx / timeouts.
* Token usage recorded per call (``last_usage``, ``total_usage``) and forwarded to an
  optional ``on_usage(model, prompt_tokens, completion_tokens)`` hook, and to
  ``procqc.pricing`` (per-stage cost).
* Optional on-disk cache keyed by (model, messages, response_format) so a re-run is free.
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from procqc import pricing
from procqc.config import config

try:
    from openai import OpenAI
    from openai import APIConnectionError, APITimeoutError, BadRequestError, RateLimitError
    from openai import APIStatusError
except ImportError as exc:  # pragma: no cover
    raise ImportError("pip install openai  (Fuelix is OpenAI-compatible)") from exc


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    cache_hits: int = 0  # responses served from the on-disk cache (no tokens billed)

    def add(self, p: int, c: int) -> None:
        self.prompt_tokens += int(p or 0)
        self.completion_tokens += int(c or 0)
        self.calls += 1


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction: handles ```json fences, prose, <think> blocks."""
    s = (text or "").strip()
    if "</think>" in s:
        s = s.split("</think>", 1)[1].strip()
    if s.startswith("```"):
        parts = s.split("```")
        s = parts[1] if len(parts) >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Outermost {...} if the text starts with an object, else outermost [...] if it starts with a
    # list. Never fall back from a broken object to an inner list: a truncated object would then
    # "parse" as some nested array (seen: objects_seen leaking out as the whole answer).
    first_obj, first_arr = s.find("{"), s.find("[")
    if first_obj != -1 and (first_arr == -1 or first_obj < first_arr):
        open_c, close_c, start = "{", "}", first_obj
    elif first_arr != -1:
        open_c, close_c, start = "[", "]", first_arr
    else:
        raise ValueError(f"no JSON object found in model output: {s[:200]!r}")
    end = s.rfind(close_c)
    if end > start:
        try:
            return json.loads(s[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"no complete JSON {open_c}{close_c} in model output (truncated?): {s[:200]!r}")


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError, TimeoutError)):
        return True
    if isinstance(exc, APIStatusError) and getattr(exc, "status_code", 0) >= 500:
        return True
    return False


def _backoff(attempt: int) -> float:
    return min(60.0, (2**attempt) + random.uniform(0, 0.5))


def _schema_format(schema: dict, name: str) -> dict:
    return {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": False}}


@dataclass
class LLMClient:
    model: str = field(default_factory=lambda: config.text_model)
    base_url: str = field(default_factory=lambda: config.fuelix_base_url)
    api_key: str = field(default_factory=lambda: config.fuelix_api_key)
    timeout: float = field(default_factory=lambda: config.call_timeout)
    max_retries: int = field(default_factory=lambda: config.max_retries)
    cache_dir: Optional[str] = field(default_factory=lambda: config.llm_cache_dir or None)
    on_usage: Optional[Callable[[str, int, int], None]] = None
    last_usage: Usage = field(default_factory=Usage)
    total_usage: Usage = field(default_factory=Usage)
    last_raw: str = ""

    def __post_init__(self) -> None:
        if not (self.api_key and self.base_url):
            raise RuntimeError("Fuelix not configured: set FUELIX_API_KEY / FUELIX_BASE_URL in .env")
        self._sync: Optional[OpenAI] = None

    # ----- client (one per instance; reuses the connection pool) ------------------
    @property
    def sync(self) -> OpenAI:
        if self._sync is None:
            self._sync = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        return self._sync

    @staticmethod
    def _truncated(resp: Any) -> bool:
        try:
            return resp.choices[0].finish_reason == "length"
        except Exception:  # noqa: BLE001
            return False

    # ----- cache --------------------------------------------------------------------
    def _cache_path(self, model: str, messages: list, rf: Optional[dict]) -> Optional[Path]:
        if not self.cache_dir:
            return None
        key = hashlib.sha256(
            json.dumps({"m": model, "msgs": messages, "rf": rf}, sort_keys=True).encode()
        ).hexdigest()
        p = Path(self.cache_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p / f"{key}.json"

    # ----- usage --------------------------------------------------------------------
    def _record(self, model: str, resp: Any) -> None:
        usage = getattr(resp, "usage", None)
        p = getattr(usage, "prompt_tokens", 0) or 0
        c = getattr(usage, "completion_tokens", 0) or 0
        details = getattr(usage, "completion_tokens_details", None)
        r = getattr(details, "reasoning_tokens", 0) or 0
        self.last_usage = Usage()
        self.last_usage.add(p, c)
        self.total_usage.add(p, c)
        try:
            from procqc import pricing
            pricing.record_usage(model, p, c, reasoning_tok=r)
        except Exception:  # noqa: BLE001 - accounting must never break a call
            pass
        if self.on_usage:
            try:
                self.on_usage(model, p, c)
            except Exception:  # noqa: BLE001
                pass

    def _record_cache_hit(self, model: str) -> None:
        self.total_usage.cache_hits += 1
        try:
            from procqc import pricing
            pricing.record_usage(model, 0, 0, cached=True)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _content(resp: Any) -> str:
        if isinstance(resp, str):  # proxy returned a bare string body (login page etc.)
            raise RuntimeError(f"Fuelix returned a non-API response: {resp[:200]!r}")
        return resp.choices[0].message.content or ""

    # ----- public API -----------------------------------------------------------------
    def complete_json(
        self,
        system: str,
        user: str,
        schema: Optional[dict] = None,
        schema_name: str = "response",
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 8000,
        use_cache: bool = True,
        reasoning_effort: Optional[str] = None,
    ) -> Any:
        """Return parsed JSON from the model. Tries json_schema -> json_object -> free text.
        reasoning_effort ("low", "medium", "high") caps hidden reasoning where the provider supports it;
        if the provider rejects the parameter, the call is retried without it."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return self.complete_json_messages(messages, schema, schema_name, model, temperature,
                                           max_tokens, use_cache, reasoning_effort)

    def complete_json_messages(
        self,
        messages: list,
        schema: Optional[dict] = None,
        schema_name: str = "response",
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 8000,
        use_cache: bool = True,
        reasoning_effort: Optional[str] = None,
    ) -> Any:
        """Same as complete_json but with a full OpenAI messages list (e.g. image parts)."""
        model = model or self.model
        formats: list = []
        if schema is not None:
            formats.append(_schema_format(schema, schema_name))
        formats += [{"type": "json_object"}, None]

        cache_model = model if not reasoning_effort else f"{model}|effort={reasoning_effort}"
        cache_p = self._cache_path(cache_model, messages, formats[0]) if use_cache else None
        if cache_p and cache_p.is_file():
            self.last_raw = cache_p.read_text()
            self._record_cache_hit(model)
            return extract_json(self.last_raw)

        last_exc: Optional[Exception] = None
        budget = max_tokens
        for rf in formats:
            for attempt in range(self.max_retries):
                try:
                    kwargs: dict = dict(model=model, messages=messages, temperature=temperature,
                                        max_tokens=budget)
                    if rf is not None:
                        kwargs["response_format"] = rf
                    if reasoning_effort:
                        kwargs["reasoning_effort"] = reasoning_effort
                    _t0 = time.time()
                    resp = self.sync.chat.completions.create(**kwargs)
                    pricing.record_call_time(time.time() - _t0, model)
                    self._record(model, resp)
                    self.last_raw = self._content(resp)
                    if self._truncated(resp) and budget < 4 * max_tokens:
                        # reasoning models spend hidden tokens from this budget; grow it and retry
                        budget *= 2
                        continue
                    data = extract_json(self.last_raw)
                    if cache_p:
                        cache_p.write_text(self.last_raw)
                    return data
                except BadRequestError as exc:
                    if reasoning_effort and "reasoning" in str(exc).lower():
                        reasoning_effort = None  # provider does not take the parameter: retry without it
                        continue
                    # unsupported response_format on this model/proxy -> next format
                    last_exc = exc
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < self.max_retries - 1 and _is_retryable(exc):
                        _w = _backoff(attempt)
                        pricing.record_retry(_w)
                        time.sleep(_w)
                        continue
                    if isinstance(exc, ValueError):  # unparseable output -> try next format
                        break
                    raise
        raise RuntimeError(f"LLM call failed after all formats/retries: {last_exc} "
                           f"| raw={self.last_raw[:200]!r}")

    def list_models(self) -> list:
        return sorted(m.id for m in self.sync.models.list().data)
