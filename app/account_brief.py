from __future__ import annotations

from typing import Any

from openai import OpenAI

from app.config import settings
from app.data_loader import load_repository_snapshot, get_account_tickets
from app.models import AccountBriefResponse, AccountPayload, RiskFlag, TicketPayload
from app.prompts import ACCOUNT_BRIEF_PROMPT_ID, ACCOUNT_BRIEF_PROMPT_TEMPLATE
from app.risk_rules import detect_account_risk_flags, detect_ticket_risk_flags
from app.utils import normalize_text


def _article_for(word: str) -> str:
    return "an" if word[:1].lower() in {"a", "e", "i", "o", "u"} else "a"


def _pluralize(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {plural or singular + 's'}"


def _find_account(account_id: str) -> AccountPayload | None:
    snapshot = load_repository_snapshot()
    return snapshot.account_map.get(account_id)


def _recent_tickets(account_id: str) -> list[TicketPayload]:
    snapshot = load_repository_snapshot()
    return get_account_tickets(
        account_id=account_id,
        tickets=snapshot.tickets,
        days=90,
        reference_date=settings.eval_reference_date,
    )


def _dedupe_flags(flags: list[RiskFlag]) -> list[RiskFlag]:
    deduped: list[RiskFlag] = []
    seen: set[tuple[str, str, str]] = set()
    for flag in flags:
        key = (flag.title, flag.severity, flag.evidence_quote)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(flag)
    return deduped


def _build_executive_summary(account: AccountPayload, recent_tickets: list[TicketPayload], risk_flags: list[RiskFlag]) -> str:
    adoption_pct = 0
    if account.seats_licensed > 0:
        adoption_pct = round((account.seats_active / account.seats_licensed) * 100)

    summary_sentences = [
        (
            f"{account.company} is a {account.plan_tier} account in {account.region} using "
            f"{', '.join(account.products)} with ARR of ${account.arr_usd:,}."
        ),
        (
            f"Current health is {account.health_status} with {_article_for(account.usage_trend.lower())} "
            f"{account.usage_trend.lower()} usage trend, {_pluralize(account.open_tickets, 'open ticket')}, "
            f"and {_pluralize(account.p1_tickets_last_30d, 'P1 ticket')} in the last 30 days."
        ),
        (
            f"Adoption is approximately {adoption_pct}% based on {account.seats_active} active seats out of "
            f"{account.seats_licensed} licensed seats."
        ),
    ]

    if recent_tickets:
        summary_sentences.append(
            f"There {'is' if len(recent_tickets) == 1 else 'are'} {_pluralize(len(recent_tickets), 'support ticket')} "
            f"in the last 90 days, indicating recent operational activity that should be reviewed before the TAM conversation."
        )

    if risk_flags:
        top_flag = risk_flags[0]
        summary_sentences.append(
            f"The most important current risk is {top_flag.title.lower()}, supported by evidence such as: \"{top_flag.evidence_quote}\"."
        )

    return " ".join(summary_sentences[:5])


def _build_talking_points(account: AccountPayload, risk_flags: list[RiskFlag], recent_tickets: list[TicketPayload]) -> list[str]:
    points: list[str] = []

    if account.usage_trend in {"Declining", "Inactive"}:
        points.append("Review adoption blockers and agree on a concrete usage recovery plan.")

    if account.escalation_notes:
        points.append("Address the escalation history directly and confirm whether stakeholder concerns are changing.")

    if account.open_tickets > 0:
        points.append("Walk through open support issues, owners, and the timeline to resolution.")

    if account.p1_tickets_last_30d > 0:
        points.append("Acknowledge recent critical incidents and explain what has changed to reduce repeat risk.")

    if any("upgrade" in normalize_text(ticket.subject + " " + ticket.body).lower() for ticket in recent_tickets):
        points.append("Explore expansion needs and confirm whether plan limits are blocking value.")

    if account.renewal_date:
        points.append(f"Prepare a renewal readout ahead of the {account.renewal_date} contract date.")

    if not points:
        points.append("Confirm current goals, success criteria, and any support or product blockers.")

    return points[:5]


def _maybe_refine_summary_with_llm(
    account: AccountPayload,
    recent_tickets: list[TicketPayload],
    response: AccountBriefResponse,
) -> AccountBriefResponse:
    if not settings.enable_llm or not settings.openai_api_key:
        return response

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        ticket_context = [
            {
                "ticket_id": ticket.ticket_id,
                "subject": ticket.subject,
                "urgency": ticket.urgency,
                "created_at": ticket.created_at.isoformat(),
            }
            for ticket in recent_tickets[:10]
        ]
        llm_response = client.responses.parse(
            model=settings.openai_model,
            temperature=settings.llm_temperature,
            input=[
                {"role": "system", "content": ACCOUNT_BRIEF_PROMPT_TEMPLATE},
                {
                    "role": "user",
                    "content": (
                        f"Prompt version: {ACCOUNT_BRIEF_PROMPT_ID}\n\n"
                        f"Account:\n{account.model_dump_json(indent=2)}\n\n"
                        f"Recent tickets:\n{ticket_context}\n\n"
                        f"Current draft:\n{response.model_dump_json(indent=2)}"
                    ),
                },
            ],
            text_format=AccountBriefResponse,
        )
        parsed = llm_response.output_parsed
        if parsed is None:
            return response
        return parsed
    except Exception:
        return response


def build_account_brief(account_id: str) -> AccountBriefResponse:
    snapshot = load_repository_snapshot()
    account = snapshot.account_map.get(account_id)
    if account is None:
        raise ValueError(f"Account '{account_id}' was not found in accounts.json.")

    recent_tickets = get_account_tickets(
        account_id=account_id,
        tickets=snapshot.tickets,
        days=90,
        reference_date=settings.eval_reference_date,
    )
    recent_tickets = sorted(recent_tickets, key=lambda ticket: (ticket.created_at, ticket.ticket_id))

    risk_flags = _dedupe_flags(
        detect_account_risk_flags(account) + detect_ticket_risk_flags(recent_tickets)
    )

    response = AccountBriefResponse(
        account_id=account.account_id,
        company=account.company,
        executive_summary=_build_executive_summary(account, recent_tickets, risk_flags),
        open_risks_and_flagged_issues=risk_flags[:8],
        recommended_talking_points=_build_talking_points(account, risk_flags, recent_tickets),
    )
    return _maybe_refine_summary_with_llm(account, recent_tickets, response)
