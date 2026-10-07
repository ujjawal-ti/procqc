"""Google AI Studio client for native video input (google-genai SDK), and the clip cutter.

The whole-video narration and every per-kind verifier send video through this client: the whole
recording once (the narration is cached and shared by the checks that read it), or short clips cut
with ffmpeg around the moments a verifier must see.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from procqc import pricing
from procqc.config import config
from procqc.llm_client import extract_json

INLINE_LIMIT = 19 * 1024 * 1024  # inline video bytes limit for generate_content


@dataclass
class GenAIVideoClient:
    api_key: str = field(default_factory=lambda: config.google_api_key)
    model: str = field(default_factory=lambda: config.google_model)
    fps: float = field(default_factory=lambda: config.google_video_fps)
    max_frames: int = 900  # long recordings are sampled more sparsely so one call stays within budget
    cache_dir: Optional[str] = field(default_factory=lambda: config.llm_cache_dir)
    temperature: float = 0.2
    max_retries: int = 7  # AI Studio returns 503 "high demand" in bursts; back off up to ~2 min
    _client: Any = field(default=None, repr=False)
    _uploads: Dict[str, Any] = field(default_factory=dict, repr=False)

    def _cl(self):
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("GOOGLE_API_KEY is not set (procqc/.env)")
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _effective_fps(self, video_path: str) -> float:
        try:
            import cv2
            c = cv2.VideoCapture(video_path)
            dur = c.get(cv2.CAP_PROP_FRAME_COUNT) / (c.get(cv2.CAP_PROP_FPS) or 30.0)
            c.release()
        except Exception:  # noqa: BLE001
            return self.fps
        if dur <= 0:
            return self.fps
        return round(min(self.fps, max(0.2, self.max_frames / dur)), 3)

    def _video_hash(self, video_path: str) -> str:
        """Cache identity of a video: content hash + sampling rate (same value the part carries)."""
        h = hashlib.sha256()
        with open(video_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:16] + f"@{self._effective_fps(video_path)}"

    def _video_part(self, video_path: str):
        from google.genai import types
        data = Path(video_path).read_bytes()
        if len(data) <= INLINE_LIMIT:
            part = types.Part.from_bytes(data=data, mime_type="video/mp4")
        else:
            if video_path not in self._uploads:
                _tu = time.time()
                f = self._cl().files.upload(file=video_path)
                for _ in range(120):
                    f = self._cl().files.get(name=f.name)
                    if getattr(f.state, "name", str(f.state)).endswith("ACTIVE"):
                        break
                    time.sleep(2)
                self._uploads[video_path] = f
                pricing.record_call_time(time.time() - _tu, None, stage="video_upload")
                pricing.record_wall("video_upload", time.time() - _tu)
            f = self._uploads[video_path]
            part = types.Part.from_uri(file_uri=f.uri, mime_type=f.mime_type or "video/mp4")
        fps = self._effective_fps(video_path)
        try:
            part.video_metadata = types.VideoMetadata(fps=fps)
        except Exception:  # noqa: BLE001 - older SDKs: default sampling
            pass
        return part

    def ask(self, video_path, system: str, user: str, schema: Dict[str, Any], stage: str) -> Dict[str, Any]:
        """video_path: one video, or a list of clips sent in order as "Clip 1", "Clip 2", ...
        The cache is checked BEFORE any upload: a cached answer never re-uploads a long video."""
        from google.genai import types
        paths = list(video_path) if isinstance(video_path, (list, tuple)) else [video_path]
        vhash = "+".join(self._video_hash(vp) for vp in paths)
        key = hashlib.sha256(json.dumps([self.model, self.fps, vhash, system, user, schema], sort_keys=True).encode()).hexdigest()
        cpath = Path(self.cache_dir) / "genai" / f"{key}.json" if self.cache_dir else None
        if cpath and cpath.exists():
            cached = json.loads(cpath.read_text())
            pricing.record_usage(self.model, 0, 0, 0, cached=True, stage=stage)
            return cached["data"]
        if isinstance(video_path, (list, tuple)):
            parts = []
            for k, vp in enumerate(paths, 1):
                parts += [f"Clip {k}:", self._video_part(vp)]
        else:
            parts = [self._video_part(video_path)]
        cfg_kwargs = dict(system_instruction=system, response_mime_type="application/json",
                          temperature=self.temperature)
        last_exc: Optional[Exception] = None
        with pricing.use_stage(stage):
            for attempt in range(self.max_retries):
                try:
                    try:
                        cfg = types.GenerateContentConfig(response_json_schema=schema, **cfg_kwargs)
                    except Exception:  # noqa: BLE001 - SDK without response_json_schema
                        cfg = types.GenerateContentConfig(**cfg_kwargs)
                    t0 = time.time()
                    resp = self._cl().models.generate_content(model=self.model, contents=parts + [user], config=cfg)
                    um = getattr(resp, "usage_metadata", None)
                    in_tok = int(getattr(um, "prompt_token_count", 0) or 0)
                    out_tok = int(getattr(um, "candidates_token_count", 0) or 0)
                    think = int(getattr(um, "thoughts_token_count", 0) or 0)
                    pricing.record_usage(self.model, in_tok, out_tok + think, think)
                    pricing.record_call_time(time.time() - t0, self.model, stage=stage)
                    data = extract_json(resp.text or "")
                    if not isinstance(data, dict):
                        raise ValueError(f"non-object JSON: {str(data)[:200]}")
                    if cpath:
                        cpath.parent.mkdir(parents=True, exist_ok=True)
                        cpath.write_text(json.dumps({"data": data, "usage": {"in": in_tok, "out": out_tok, "thoughts": think},
                                                     "model": self.model, "fps": self.fps}))
                    return data
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    wait = min(120.0, 4.0 * (2 ** attempt))  # 4, 8, 16, 32, 64, 120, 120 s
                    pricing.record_retry(wait, stage=stage)
                    time.sleep(wait)
        raise RuntimeError(f"genai call failed after {self.max_retries} attempts: {last_exc!r}")


def cut_clip(video_path: str, start: float, end: float, out_dir: Path) -> str:
    """[start, end] of a video as a small H.264 clip, 720 p, no audio (cached by source name and window)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{Path(video_path).stem}_{start:.1f}-{end:.1f}.mp4"
    if not dst.exists():
        # write to a unique temporary name and rename when complete: parallel runs that need the same
        # clip must never read a half-written file
        tmp = dst.with_name(f".{dst.stem}.{uuid.uuid4().hex[:8]}.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", video_path,
                        "-t", f"{end - start:.3f}", "-an", "-vf", "scale=-2:720", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "26", str(tmp)], check=True)
        os.replace(tmp, dst)
    return str(dst)
