"""LLMClient's real call path against a fake provider: accounting, call time, retries, cache."""
import types

from procqc import pricing
from procqc.llm_client import LLMClient


def _resp(text='{"ok": true}', p=100, c=20, r=5):
    usage = types.SimpleNamespace(prompt_tokens=p, completion_tokens=c,
                                  completion_tokens_details=types.SimpleNamespace(reasoning_tokens=r))
    msg = types.SimpleNamespace(content=text)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg, finish_reason="stop")], usage=usage)


class _Completions:
    def __init__(self, fail_first=0):
        self.n = 0
        self.fail_first = fail_first

    def create(self, **kw):
        self.n += 1
        if self.n <= self.fail_first:
            raise TimeoutError("simulated timeout")
        return _resp()


def _client(tmp_path, fail_first=0):
    c = LLMClient(api_key="k", base_url="http://fake", model="gemini-3.8-flash", cache_dir=str(tmp_path))
    c._sync = types.SimpleNamespace(chat=types.SimpleNamespace(completions=_Completions(fail_first)))
    return c


def test_call_records_tokens_and_call_time(tmp_path):
    c = _client(tmp_path)
    m = pricing.CostMeter()
    with pricing.use_meter(m), pricing.timed_stage("unit"):
        out = c.complete_json("sys", "user", use_cache=False)
    assert out == {"ok": True}
    row = m.snapshot()["by_stage"]["unit"]
    assert row["calls"] == 1 and row["prompt_tokens"] == 100 and row["reasoning_tokens"] == 5
    assert row["call_time_s"] >= 0.0 and row["wall_s"] >= row["call_time_s"] - 1e-6


def test_retry_wait_is_recorded(tmp_path, monkeypatch):
    import procqc.llm_client as L
    monkeypatch.setattr(L, "_is_retryable", lambda exc: True)
    monkeypatch.setattr(L, "_backoff", lambda attempt: 0.0)
    c = _client(tmp_path, fail_first=1)
    m = pricing.CostMeter()
    with pricing.use_meter(m), pricing.use_stage("unit_retry"):
        out = c.complete_json("sys", "user", use_cache=False)
    assert out == {"ok": True}
    row = m.snapshot()["by_stage"]["unit_retry"]
    assert row["n_retries"] == 1 and row["calls"] == 1


def test_cache_hit_makes_no_call(tmp_path):
    c = _client(tmp_path)
    assert c.complete_json("sys", "user") == {"ok": True}
    m = pricing.CostMeter()
    with pricing.use_meter(m), pricing.use_stage("unit_cache"):
        assert c.complete_json("sys", "user") == {"ok": True}
    assert c._sync.chat.completions.n == 1
    assert m.snapshot()["by_stage"]["unit_cache"]["cache_hits"] == 1
