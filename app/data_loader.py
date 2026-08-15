from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, KNOWLEDGE_BASE_DIR, settings
from app.models import AccountPayload, KnowledgeBaseDocument, TicketPayload
from app.utils import ensure_utc, parse_iso_date, parse_iso_datetime


@dataclass(frozen=True)
class RepositorySnapshot:
    tickets: list[TicketPayload]
    accounts: list[AccountPayload]
    account_map: dict[str, AccountPayload]
    kb_documents: list[KnowledgeBaseDocument]


def _read_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_text_file(path: Path) -> str:
    with path.open("r", encoding="utf-8") as handle:
        return handle.read()


def _coerce_ticket(record: dict[str, Any]) -> TicketPayload:
    payload = dict(record)
    payload["created_at"] = parse_iso_datetime(payload["created_at"])
    payload["updated_at"] = parse_iso_datetime(payload["updated_at"])
    return TicketPayload.model_validate(payload)


def _coerce_account(record: dict[str, Any]) -> AccountPayload:
    return AccountPayload.model_validate(record)


def _kb_category_from_path(path: Path) -> str:
    try:
        return path.relative_to(KNOWLEDGE_BASE_DIR).parts[0]
    except ValueError:
        return path.parent.name


def _extract_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def _resolve_reference_datetime(reference_date: str | datetime | None = None) -> datetime:
    if isinstance(reference_date, datetime):
        return ensure_utc(reference_date)

    if isinstance(reference_date, str):
        return datetime.combine(parse_iso_date(reference_date), datetime.min.time(), tzinfo=timezone.utc)

    return datetime.combine(
        parse_iso_date(settings.eval_reference_date),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )


def load_tickets(path: Path | None = None) -> list[TicketPayload]:
    ticket_path = path or DATA_DIR / "tickets.json"
    records = _read_json_file(ticket_path)
    return [_coerce_ticket(record) for record in records]


def load_accounts(path: Path | None = None) -> list[AccountPayload]:
    account_path = path or DATA_DIR / "accounts.json"
    records = _read_json_file(account_path)
    return [_coerce_account(record) for record in records]


def build_account_map(accounts: list[AccountPayload]) -> dict[str, AccountPayload]:
    return {account.account_id: account for account in accounts}


def get_account_tickets(
    account_id: str,
    tickets: list[TicketPayload],
    days: int = 90,
    reference_date: str | datetime | None = None,
) -> list[TicketPayload]:
    reference_dt = _resolve_reference_datetime(reference_date)
    cutoff = reference_dt - timedelta(days=days)

    filtered = [
        ticket
        for ticket in tickets
        if ticket.account_id == account_id and ensure_utc(ticket.created_at) >= cutoff
    ]
    return sorted(filtered, key=lambda ticket: (ticket.created_at, ticket.ticket_id))


def load_kb_documents(base_dir: Path | None = None) -> list[KnowledgeBaseDocument]:
    kb_dir = base_dir or KNOWLEDGE_BASE_DIR
    documents: list[KnowledgeBaseDocument] = []

    for path in sorted(kb_dir.rglob("*.md")):
        content = _read_text_file(path)
        relative_path = path.relative_to(kb_dir).as_posix()
        documents.append(
            KnowledgeBaseDocument(
                path=relative_path,
                category=_kb_category_from_path(path),
                title=_extract_title(content, path.stem),
                content=content,
            )
        )

    return documents


def load_repository_snapshot() -> RepositorySnapshot:
    tickets = load_tickets()
    accounts = load_accounts()
    account_map = build_account_map(accounts)
    kb_documents = load_kb_documents()
    return RepositorySnapshot(
        tickets=tickets,
        accounts=accounts,
        account_map=account_map,
        kb_documents=kb_documents,
    )
