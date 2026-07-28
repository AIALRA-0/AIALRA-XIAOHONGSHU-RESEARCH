#!/usr/bin/env python3
"""Deterministic helpers for Xiaohongshu multi-round research."""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from decimal import Decimal
from typing import Any
from urllib.parse import quote_plus, urlsplit


ALLOWED_HOST = "www.xiaohongshu.com"
NOTE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{12,40}$")
EPHEMERAL_TOKEN_RE = re.compile(r"\bxsec_token\b", re.IGNORECASE)


def normalized_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def note_id_from_url(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = urlsplit(raw.strip())
    except ValueError:
        return None
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != ALLOWED_HOST:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] not in {"explore", "search_result"}:
        return None
    return parts[1] if NOTE_ID_RE.fullmatch(parts[1]) else None


def canonical_note_url(raw: Any, note_id: Any = None) -> str | None:
    identifier = str(note_id) if note_id is not None else note_id_from_url(raw)
    if not NOTE_ID_RE.fullmatch(identifier or ""):
        return None
    if isinstance(raw, str):
        try:
            parsed = urlsplit(raw.strip())
        except ValueError:
            return None
        if parsed.scheme != "https" or (parsed.hostname or "").lower() != ALLOWED_HOST:
            return None
    return f"https://{ALLOWED_HOST}/explore/{identifier}"


def contains_ephemeral_token(value: Any) -> bool:
    if isinstance(value, str):
        return EPHEMERAL_TOKEN_RE.search(value) is not None
    if isinstance(value, dict):
        return any(
            contains_ephemeral_token(key) or contains_ephemeral_token(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return any(contains_ephemeral_token(item) for item in value)
    return False


def official_search_url(query: str) -> str:
    return f"https://{ALLOWED_HOST}/search_result?keyword={quote_plus(query)}"


def parse_engagement(value: Any) -> Decimal:
    text = normalized_text(value).replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([万wk]?)", text)
    if not match:
        return Decimal("0")
    number = Decimal(match.group(1))
    unit = match.group(2)
    if unit in {"万", "w"}:
        number *= 10000
    elif unit == "k":
        number *= 1000
    return number


def parse_aware_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def time_is_fresh(value: Any, *, hours: int = 24) -> bool:
    parsed = parse_aware_time(value)
    if parsed is None:
        return False
    age = dt.datetime.now(dt.timezone.utc) - parsed.astimezone(dt.timezone.utc)
    return -dt.timedelta(minutes=5) <= age <= dt.timedelta(hours=hours)


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value
