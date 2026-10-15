"""Internal data access: FTS reviewer labels (read-only SQL), S3 clip download, and the headset manifest.

Credentials and the names of internal resources (bucket, workflow, tables) come from procqc/.env (see
.env.example), never from the code; install the extra with `pip install -e .[internal]`.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

ENV = Path(__file__).resolve().parents[1] / ".env"
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


def setting(key: str, default: Optional[str] = None) -> str:
    """A value from procqc/.env (or the environment); stops with the key's name when it is not set."""
    from dotenv import dotenv_values
    v = (dotenv_values(ENV) if ENV.exists() else {}).get(key) or os.environ.get(key) or default
    if not v:
        raise SystemExit(f"{key} is not set: add it to {ENV} (see .env.example)")
    return v


def sql_name(key: str, default: Optional[str] = None) -> str:
    """A schema or schema.table name from settings, checked to be a plain identifier before it enters SQL."""
    v = setting(key, default)
    if not _IDENT.match(v):
        raise SystemExit(f"{key} must be a plain name or schema.table name")
    return v
