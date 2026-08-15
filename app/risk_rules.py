from __future__ import annotations

from dataclasses import dataclass

from app.models import AccountPayload, RiskFlag, TicketPayload, UrgencyTier
from app.utils import normalize_text, truncate_text


@dataclass(frozen=True)
class RiskSignal:
    title: str
    severity: str
    rationale: str
    evidence_quote: str
    source_ticket_id: str | None = None


TICKET_RISK_PATTERNS = [
    (
        "Blocked users",
        "high",
        "Ticket indicates user access is blocked or unavailable.",
        ("blocked", "unable to log in", "can't authenticate", "cannot authenticate", "can't access", "cannot access"),
    ),
    (
        "Data loss risk",
        "critical",
        "Ticket suggests missing, corrupted, or unrecoverable data.",
        ("missing records", "data loss", "corrupted", "recover the missing", "restore sync", "discrepancy"),
    ),
    (
        "Escalation sentiment",
        "high",
        "Ticket language indicates urgency, frustration, or business impact.",
        ("urgent", "urgently", "asap", "critical issue", "impacting", "please advise urgently", "frustrated"),
    ),
    (
        "Repeated outage signal",
        "high",
        "Ticket points to sustained service failure or repeated delivery issues.",
        ("failed deliveries", "stopped syncing", "not being delivered", "timing out", "service has been failing"),
    ),
    (
        "Commercial expansion or churn signal",
        "medium",
        "Ticket mentions upgrade pressure, vendor review, or plan friction.",
        ("upgrade", "competing vendor", "pricing", "credit", "refund", "outgrown our current"),
    ),
]


def _ticket_quote(ticket: TicketPayload, matched_phrase: str) -> str:
    raw_sentences = [
        normalize_text(sentence)
        for sentence in ticket.body.replace("\n", " ").split(".")
        if normalize_text(sentence)
    ]
    phrase = matched_phrase.lower()

    matched_sentences = [sentence for sentence in raw_sentences if phrase in sentence.lower()]
    if matched_sentences:
        quote = ". ".join(matched_sentences[:2]).strip()
        if not quote.endswith("."):
            quote += "."
        return truncate_text(quote, limit=180)

    body = normalize_text(ticket.body)
    lowered = body.lower()
    idx = lowered.find(phrase)
    if idx == -1:
        return truncate_text(body, limit=180)

    start = max(0, idx)
    end = min(len(body), idx + len(matched_phrase) + 120)
    quote = body[start:end].strip()
    return truncate_text(quote, limit=180)


def detect_ticket_risk_flags(tickets: list[TicketPayload]) -> list[RiskFlag]:
    flags: list[RiskFlag] = []
    seen_keys: set[tuple[str, str | None]] = set()

    for ticket in tickets:
        lowered = normalize_text(ticket.subject + " " + ticket.body).lower()

        if ticket.urgency in {UrgencyTier.P1.value, UrgencyTier.P2.value}:
            key = ("High-severity support pattern", ticket.ticket_id)
            if key not in seen_keys:
                seen_keys.add(key)
                flags.append(
                    RiskFlag(
                        title="High-severity support pattern",
                        severity="high" if ticket.urgency == UrgencyTier.P2.value else "critical",
                        rationale=f"Recent {ticket.urgency} ticket indicates elevated support risk.",
                        evidence_quote=truncate_text(normalize_text(ticket.subject), limit=180),
                        source_ticket_id=ticket.ticket_id,
                    )
                )

        for title, severity, rationale, patterns in TICKET_RISK_PATTERNS:
            matched = next((pattern for pattern in patterns if pattern in lowered), None)
            if not matched:
                continue

            key = (title, ticket.ticket_id)
            if key in seen_keys:
                continue

            seen_keys.add(key)
            flags.append(
                RiskFlag(
                    title=title,
                    severity=severity,
                    rationale=rationale,
                    evidence_quote=_ticket_quote(ticket, matched),
                    source_ticket_id=ticket.ticket_id,
                )
            )

    flags.sort(key=lambda flag: (flag.severity, flag.title, flag.source_ticket_id or ""))
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    flags.sort(key=lambda flag: (severity_rank.get(flag.severity, 99), flag.title, flag.source_ticket_id or ""))
    return flags


def detect_account_risk_flags(account: AccountPayload) -> list[RiskFlag]:
    flags: list[RiskFlag] = []

    if account.health_status in {"At Risk", "Churning"}:
        flags.append(
            RiskFlag(
                title="Account health is below healthy",
                severity="critical" if account.health_status == "Churning" else "high",
                rationale=f"Account health status is marked as {account.health_status}.",
                evidence_quote=f"health_status={account.health_status}",
                source_ticket_id=None,
            )
        )

    if account.usage_trend in {"Declining", "Inactive"}:
        flags.append(
            RiskFlag(
                title="Usage trend is weakening",
                severity="high",
                rationale=f"Usage trend is {account.usage_trend}, which may indicate adoption risk.",
                evidence_quote=f"usage_trend={account.usage_trend}",
                source_ticket_id=None,
            )
        )

    if account.p1_tickets_last_30d > 0:
        flags.append(
            RiskFlag(
                title="Recent P1 history",
                severity="critical" if account.p1_tickets_last_30d >= 2 else "high",
                rationale="Recent critical incidents raise escalation risk ahead of TAM engagement.",
                evidence_quote=f"p1_tickets_last_30d={account.p1_tickets_last_30d}",
                source_ticket_id=None,
            )
        )

    if account.open_tickets >= 5:
        flags.append(
            RiskFlag(
                title="High open ticket load",
                severity="medium",
                rationale="Open support load is elevated and may affect account sentiment.",
                evidence_quote=f"open_tickets={account.open_tickets}",
                source_ticket_id=None,
            )
        )

    for note in account.escalation_notes:
        lowered = note.lower()
        severity = "medium"
        if "competing vendor" in lowered or "champion left" in lowered:
            severity = "critical"
        elif "frustration" in lowered or "negative sentiment" in lowered or "skipped" in lowered:
            severity = "high"

        flags.append(
            RiskFlag(
                title="Escalation note",
                severity=severity,
                rationale="Account escalation notes contain a direct risk or sentiment signal.",
                evidence_quote=truncate_text(note, limit=180),
                source_ticket_id=None,
            )
        )

    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    flags.sort(key=lambda flag: (severity_rank.get(flag.severity, 99), flag.title, flag.evidence_quote))
    return flags
