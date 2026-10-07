"""Per-stage token and cost accounting.

Every model call made through `procqc.llm_client.LLMClient` or `procqc.video_client.GenAIVideoClient`
reports its usage here. The active
CostMeter and the current stage name live in context variables, so stages tag their calls with
`with use_stage("omission_verify"):` and episodes collect into their own meter with `with use_meter(m):`.
Thread-safe in the batch runner because context variables are per thread (and asyncio.run copies
the context into its loop).

PRICES are USD per 1M tokens, list prices as of 2026-09-21. Gemini
3.x Flash prices are promotional through 2026-12-31. Unknown models cost 0 and are flagged
`estimated` so a missing price never breaks a run. Image/video tokens are billed inside prompt
tokens by every provider used here, so no special-casing is needed.
"""
from __future__ import annotations

import contextlib
import contextvars
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

PRICES: Dict[str, Dict[str, float]] = {
    # Google (via Fuelix or AI Studio)
    "gemini-3.8-flash": {"in": 0.75, "out": 3.75},
    "gemini-3.7-flash": {"in": 0.75, "out": 3.75},
    "gemini-3.6-flash": {"in": 0.75, "out": 3.75},
    "gemini-3.5-flash": {"in": 1.50, "out": 9.00},
    "gemini-3.5-flash-lite": {"in": 0.30, "out": 2.50},
    "gemini-3.1-flash-lite": {"in": 0.25, "out": 1.50},
    "gemini-3.1-pro": {"in": 2.00, "out": 12.00},
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50},
    "gemini-2.5-flash-lite": {"in": 0.10, "out": 0.40},
    "gemini-2.5-pro": {"in": 1.25, "out": 10.00},
    # Anthropic
    "claude-fable-5-1": {"in": 10.00, "out": 50.00},
    "claude-opus-5": {"in": 5.00, "out": 25.00},
    "claude-sonnet-5": {"in": 2.00, "out": 10.00},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00},
    "claude-sonnet-4-5": {"in": 3.00, "out": 15.00},
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00},
    # OpenAI (GPT-5.6 tiers)
    "gpt-5.6-sol": {"in": 5.00, "out": 30.00},
    "gpt-5.6-terra": {"in": 2.00, "out": 12.00},
    "gpt-5.6-luna": {"in": 0.20, "out": 1.20},
    # self-hosted: compute only
    "qwen": {"in": 0.0, "out": 0.0},
}



def price_for(model: Optional[str]) -> Optional[Dict[str, float]]:
    if not model:
        return None
    if model in PRICES:
        return PRICES[model]
    m = model.lower()
    for key, price in sorted(PRICES.items(), key=lambda kv: -len(kv[0])):  # longest key first
        if key in m:
            return price
    if m.startswith("qwen"):
        return PRICES["qwen"]
    return None


def cost_usd(model: Optional[str], in_tok: int, out_tok: int):
    """(usd, estimated). estimated=True when the model has no price (usd=0)."""
    price = price_for(model)
    if price is None:
        return 0.0, True
    return (in_tok / 1e6) * price["in"] + (out_tok / 1e6) * price["out"], False


def _empty_row() -> dict:
    """One accounting row per stage (or per model).
    wall_s        elapsed time of the stage as measured around it (timed_stage); concurrent calls overlap
    call_time_s   sum of the durations of the individual provider calls (>= wall_s when calls run concurrently)
    retry_wait_s  time spent sleeping between retries (503s, timeouts); NOT included in call_time_s
    n_retries     number of retried attempts"""
    return {"calls": 0, "cache_hits": 0, "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0,
            "usd": 0.0, "wall_s": 0.0, "call_time_s": 0.0, "retry_wait_s": 0.0, "n_retries": 0}


_FLOAT_KEYS = ("usd", "wall_s", "call_time_s", "retry_wait_s")


def _round_row(r: dict) -> dict:
    return {k: (round(v, 6) if k == "usd" else (round(v, 2) if k in _FLOAT_KEYS else v)) for k, v in r.items()}


@dataclass
class CostMeter:
    by_stage: Dict[str, dict] = field(default_factory=dict)
    by_model: Dict[str, dict] = field(default_factory=dict)
    estimated: bool = False
    # checks may call models from worker threads into one meter; the counters are read-modify-write
    _lock: Any = field(default_factory=threading.RLock, repr=False, compare=False)

    def add(self, model: Optional[str], in_tok: int, out_tok: int, stage: str, reasoning_tok: int = 0,
            cached: bool = False) -> None:
        in_tok, out_tok, reasoning_tok = int(in_tok or 0), int(out_tok or 0), int(reasoning_tok or 0)
        usd, est = (0.0, False) if cached else cost_usd(model, in_tok, out_tok)
        with self._lock:
            self.estimated = self.estimated or est
            for table, key in ((self.by_stage, stage or "other"), (self.by_model, model or "unknown")):
                row = table.setdefault(key, _empty_row())
                if cached:
                    row["cache_hits"] += 1
                else:
                    row["calls"] += 1
                    row["prompt_tokens"] += in_tok
                    row["completion_tokens"] += out_tok
                    row["reasoning_tokens"] += reasoning_tok
                    row["usd"] += usd

    def add_wall(self, stage: str, seconds: float) -> None:
        with self._lock:
            self.by_stage.setdefault(stage, _empty_row())["wall_s"] += float(seconds)

    def add_call_time(self, stage: str, seconds: float, model: Optional[str] = None) -> None:
        with self._lock:
            self.by_stage.setdefault(stage or "other", _empty_row())["call_time_s"] += float(seconds)
            if model:
                self.by_model.setdefault(model, _empty_row())["call_time_s"] += float(seconds)

    def add_retry(self, stage: str, wait_s: float) -> None:
        with self._lock:
            row = self.by_stage.setdefault(stage or "other", _empty_row())
            row["retry_wait_s"] += float(wait_s)
            row["n_retries"] += 1

    def total(self) -> dict:
        tot = _empty_row()
        for row in self.by_stage.values():
            for k in tot:
                tot[k] += row[k]
        return tot

    def snapshot(self) -> dict:
        tot = self.total()
        return {
            "currency": "USD", "estimated": self.estimated,
            "total": _round_row(tot),
            "by_stage": {s: _round_row(r) for s, r in self.by_stage.items()},
            "by_model": {m: _round_row(r) for m, r in self.by_model.items()},
        }

    def merge(self, other: "CostMeter") -> None:
        for table_name in ("by_stage", "by_model"):
            mine, theirs = getattr(self, table_name), getattr(other, table_name)
            for key, row in theirs.items():
                dst = mine.setdefault(key, _empty_row())
                for k, v in row.items():
                    dst[k] = dst.get(k, 0) + v
        self.estimated = self.estimated or other.estimated


def format_cost(snap: dict) -> str:
    lines = [f"{'stage':22s} {'calls':>5s} {'cached':>6s} {'prompt':>9s} {'compl':>8s} {'reason':>7s} {'usd':>9s} "
             f"{'wall_s':>7s} {'call_s':>7s} {'retry_s':>7s} {'retries':>7s}"]
    for s, r in snap["by_stage"].items():
        lines.append(f"{s:22s} {r['calls']:5d} {r['cache_hits']:6d} {r['prompt_tokens']:9d} {r['completion_tokens']:8d} "
                     f"{r['reasoning_tokens']:7d} {r['usd']:9.4f} {r['wall_s']:7.1f} {r.get('call_time_s', 0):7.1f} {r.get('retry_wait_s', 0):7.1f} {r.get('n_retries', 0):7d}")
    t = snap["total"]
    lines.append(f"{'TOTAL':22s} {t['calls']:5d} {t['cache_hits']:6d} {t['prompt_tokens']:9d} {t['completion_tokens']:8d} "
                 f"{t['reasoning_tokens']:7d} {t['usd']:9.4f} {t['wall_s']:7.1f}" + ("  (some models unpriced)" if snap["estimated"] else ""))
    return "\n".join(lines)


# ----- context plumbing -------------------------------------------------------------------
GLOBAL_METER = CostMeter()  # collects everything not inside an explicit use_meter()
_ACTIVE: contextvars.ContextVar[Optional[CostMeter]] = contextvars.ContextVar("procqc_cost_meter", default=None)
_STAGE: contextvars.ContextVar[str] = contextvars.ContextVar("procqc_cost_stage", default="other")


@contextlib.contextmanager
def use_meter(meter: CostMeter):
    tok = _ACTIVE.set(meter)
    try:
        yield meter
    finally:
        _ACTIVE.reset(tok)


@contextlib.contextmanager
def use_stage(stage: str):
    tok = _STAGE.set(stage)
    try:
        yield
    finally:
        _STAGE.reset(tok)


def current_stage() -> str:
    return _STAGE.get()


def active_meter() -> CostMeter:
    return _ACTIVE.get() or GLOBAL_METER


def record_usage(model: Optional[str], in_tok: int, out_tok: int, reasoning_tok: int = 0,
                 cached: bool = False, stage: Optional[str] = None) -> None:
    """Called by the LLM client. Attributes to the active meter (and always to GLOBAL_METER)."""
    st = stage or _STAGE.get()
    meter = _ACTIVE.get()
    if meter is not None:
        meter.add(model, in_tok, out_tok, st, reasoning_tok, cached)
    GLOBAL_METER.add(model, in_tok, out_tok, st, reasoning_tok, cached)


def record_wall(stage: str, seconds: float) -> None:
    meter = _ACTIVE.get()
    if meter is not None:
        meter.add_wall(stage, seconds)
    GLOBAL_METER.add_wall(stage, seconds)


def record_call_time(seconds: float, model: Optional[str] = None, stage: Optional[str] = None) -> None:
    """Duration of one provider call (request sent -> response received), attributed to the active stage."""
    st = stage or _STAGE.get()
    meter = _ACTIVE.get()
    if meter is not None:
        meter.add_call_time(st, seconds, model)
    GLOBAL_METER.add_call_time(st, seconds, model)


def record_retry(wait_s: float, stage: Optional[str] = None) -> None:
    """A retry is about to happen after sleeping wait_s; kept separate from call time."""
    st = stage or _STAGE.get()
    meter = _ACTIVE.get()
    if meter is not None:
        meter.add_retry(st, wait_s)
    GLOBAL_METER.add_retry(st, wait_s)


def _pct(values, q: float) -> Optional[float]:
    if not values:
        return None
    v = sorted(values)
    k = max(0, min(len(v) - 1, int(round(q * (len(v) - 1)))))
    return round(v[k], 2)


def latency_stats(values) -> Optional[dict]:
    vals = [float(x) for x in values if x is not None]
    if not vals:
        return None
    return {"n": len(vals), "mean": round(sum(vals) / len(vals), 2), "p50": _pct(vals, 0.5), "p95": _pct(vals, 0.95),
            "max": round(max(vals), 2), "sum": round(sum(vals), 2)}


def latency_report(episodes) -> dict:
    """Per-stage and end-to-end latency across episodes. `episodes` are verdict dicts with `cost.by_stage`
    rows and `timing_s.end_to_end_s` (or the legacy `timing_s.total`). Works on old verdicts too: fields
    that were not recorded then simply come out as None."""
    stages: Dict[str, Dict[str, list]] = {}
    e2e, video_s = [], []
    for v in episodes:
        t = v.get("timing_s") or {}
        e2e.append(t.get("end_to_end_s", t.get("total")))
        d = (v.get("localization") or {}).get("duration")
        if d:
            video_s.append(d)
        for s, row in ((v.get("cost") or {}).get("by_stage") or {}).items():
            acc = stages.setdefault(s, {"wall_s": [], "call_time_s": [], "retry_wait_s": [], "n_retries": [], "calls": []})
            for k in acc:
                if k in row:
                    acc[k].append(row[k])
    per_stage = {}
    for s, acc in stages.items():
        per_stage[s] = {k: latency_stats(vals) for k, vals in acc.items()}
    rep = {"n_episodes": len(episodes), "end_to_end_s": latency_stats(e2e), "per_stage": per_stage}
    if video_s and any(x is not None for x in e2e):
        ratios = [d / t for d, t in zip(video_s, e2e) if t]
        rep["realtime_factor"] = latency_stats(ratios)  # video seconds processed per wall second
    return rep


def format_latency(rep: dict) -> str:
    L = [f"latency over {rep['n_episodes']} episodes (seconds)"]
    e = rep.get("end_to_end_s")
    if e:
        L.append(f"  end-to-end: p50 {e['p50']}  p95 {e['p95']}  mean {e['mean']}  max {e['max']}")
    rf = rep.get("realtime_factor")
    if rf:
        L.append(f"  realtime factor (video s per wall s): p50 {rf['p50']}  mean {rf['mean']}")
    L.append(f"  {'stage':22s} {'wall p50':>9s} {'wall p95':>9s} {'call p50':>9s} {'retry sum':>10s} {'retries':>8s}")
    for s, r in rep["per_stage"].items():
        w, c, rw, nr = r.get("wall_s"), r.get("call_time_s"), r.get("retry_wait_s"), r.get("n_retries")
        f = lambda x, k: ("-" if not x or x.get(k) is None else f"{x[k]:.1f}")  # noqa: E731
        L.append(f"  {s:22s} {f(w,'p50'):>9s} {f(w,'p95'):>9s} {f(c,'p50'):>9s} {f(rw,'sum'):>10s} {f(nr,'sum'):>8s}")
    return "\n".join(L)


@contextlib.contextmanager
def timed_stage(stage: str):
    """use_stage + wall-clock accounting in one."""
    import time
    t0 = time.time()
    with use_stage(stage):
        try:
            yield
        finally:
            record_wall(stage, time.time() - t0)
