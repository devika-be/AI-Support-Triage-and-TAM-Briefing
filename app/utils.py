from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Iterable, TypeVar


T = TypeVar("T")

WHITESPACE_RE = re.compile(r"\s+")
ERROR_CODE_RE = re.compile(r"\b(?:ERR_[A-Z0-9_]+|[A-Z]+_[A-Z0-9_]+)\b")


def parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def clean_multiline_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def merge_subject_body(subject: str | None, body: str) -> str:
    subject = (subject or "").strip()
    body = body.strip()
    if not subject:
        return body
    return f"{subject}\n\n{body}"


def extract_error_codes(text: str) -> list[str]:
    seen: set[str] = set()
    codes: list[str] = []
    for match in ERROR_CODE_RE.findall(text):
        if match not in seen:
            seen.add(match)
            codes.append(match)
    return codes


def sort_by_stable_key(values: Iterable[T], key) -> list[T]:
    return sorted(values, key=key)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def truncate_text(text: str, limit: int = 280) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
