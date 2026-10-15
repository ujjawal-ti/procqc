"""Serve a built demo locally: the site folder, and /video/<id> from its videos.json with byte ranges
(browsers need range requests to seek in a video). Only the listed videos are reachable.

Usage (from the repository root):
  python3 -m procqc.demo.serve SITE [--port 8765]
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Sequence

CHUNK = 1 << 20


class Handler(SimpleHTTPRequestHandler):
    videos: dict = {}

    def log_message(self, fmt, *args):  # quiet: one line per error only
        if args and str(args[1])[:1] in "45":
            super().log_message(fmt, *args)

    def do_GET(self):
        m = re.fullmatch(r"/video/([0-9a-f]{6,40})", self.path.split("?")[0])
        if not m:
            return super().do_GET()
        path = self.videos.get(m.group(1))
        if not path or not os.path.isfile(path):
            return self.send_error(404, "unknown video")
        size = os.path.getsize(path)
        start, end = 0, size - 1
        rng = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "") or "")
        if rng and (rng.group(1) or rng.group(2)):
            if rng.group(1):
                start = int(rng.group(1))
                end = min(int(rng.group(2)), size - 1) if rng.group(2) else size - 1
            else:  # suffix range: the last N bytes
                start = max(0, size - int(rng.group(2)))
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                return self.end_headers()
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(path, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    buf = fh.read(min(CHUNK, left))
                    if not buf:
                        break
                    self.wfile.write(buf)
                    left -= len(buf)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser cancels range reads while seeking


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="procqc.demo.serve", description=__doc__.split("\n\n")[0])
    ap.add_argument("site")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args(argv)
    site = Path(a.site).resolve()
    Handler.videos = json.loads((site / "videos.json").read_text())
    srv = ThreadingHTTPServer((a.host, a.port), partial(Handler, directory=str(site)))
    print(f"serving {site} on http://{a.host}:{a.port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
