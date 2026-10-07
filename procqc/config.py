"""Environment-backed configuration.

All secrets and defaults live here so no other module reads os.environ directly.
Loaded once at import time from a .env file next to this package (or the CWD).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    # override=True: the .env is authoritative over stale shell exports.
    _here = Path(__file__).resolve().parent
    load_dotenv(_here / ".env", override=True)
    load_dotenv(override=False)  # also pick up a .env in the CWD, without overriding
except ImportError:  # python-dotenv not installed: rely on the process environment
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Config:
    # Fuelix (OpenAI-compatible proxy): text calls and frame / crop calls
    fuelix_api_key: str = os.environ.get("FUELIX_API_KEY", "")
    fuelix_base_url: str = os.environ.get("FUELIX_BASE_URL", "https://api.fuelix.ai/v1")
    text_model: str = os.environ.get("PROCQC_TEXT_MODEL", "gemini-3.8-flash")

    # Google AI Studio (google-genai SDK): native video input (narration, verifier clips)
    google_api_key: str = os.environ.get("GOOGLE_API_KEY", "")
    google_model: str = os.environ.get("GOOGLE_GENAI_MODEL", "gemini-3.8-flash")
    google_video_fps: float = _float("GOOGLE_VIDEO_FPS", 5.0)

    # LLM call behaviour
    call_timeout: float = _float("PROCQC_CALL_TIMEOUT", 180.0)
    max_retries: int = _int("PROCQC_MAX_RETRIES", 4)
    # On-disk JSON cache for model responses (keyed by model + messages). Empty = disabled.
    llm_cache_dir: str = os.environ.get("PROCQC_LLM_CACHE_DIR", str(Path(__file__).parent / ".llm_cache"))

    @property
    def google_configured(self) -> bool:
        return bool(self.google_api_key)

    @property
    def fuelix_configured(self) -> bool:
        return bool(self.fuelix_api_key and self.fuelix_base_url)


config = Config()
