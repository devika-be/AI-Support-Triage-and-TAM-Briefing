from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from app.config import settings
from app.models import ProductName, TicketCategory, TicketInput, TriageResponse, UrgencyTier
from app.prompts import TRIAGE_PROMPT_ID, TRIAGE_PROMPT_TEMPLATE
from app.retrieval import RetrievalResult, retrieve_relevant_kb
from app.utils import clean_multiline_text, merge_subject_body, normalize_text, truncate_text


PRODUCT_KEYWORDS = {
    ProductName.DATABRIDGE_PRO.value: {"databridge pro", "databridge", "pipeline", "connector", "schema"},
    ProductName.CLOUDSYNC.value: {"cloudsync", "sync", "bandwidth", "permissions", "conflict"},
    ProductName.ANALYTICSHUB.value: {"analyticshub", "dashboard", "report", "data sources", "alert", "export"},
    ProductName.SECUREVAULT.value: {"securevault", "vault", "key management", "audit logs", "sso", "encryption"},
    ProductName.WORKFLOWENGINE.value: {"workflowengine", "workflow", "trigger", "action", "cron", "template"},
}

PRODUCT_EXACT_PATTERNS = {
    ProductName.DATABRIDGE_PRO.value: ["databridge pro"],
    ProductName.CLOUDSYNC.value: ["cloudsync"],
    ProductName.ANALYTICSHUB.value: ["analyticshub", "analyticshub"],
    ProductName.SECUREVAULT.value: ["securevault"],
    ProductName.WORKFLOWENGINE.value: ["workflowengine"],
}

PRODUCT_AREAS = {
    ProductName.DATABRIDGE_PRO.value: [
        "Data Ingestion",
        "Schema Management",
        "Pipeline Monitoring",
        "Connectors",
        "API",
    ],
    ProductName.CLOUDSYNC.value: [
        "File Sync",
        "Conflict Resolution",
        "Permissions",
        "Bandwidth Limits",
        "Integrations",
    ],
    ProductName.ANALYTICSHUB.value: [
        "Dashboard",
        "Reports",
        "Data Sources",
        "Alerts",
        "Exports",
    ],
    ProductName.SECUREVAULT.value: [
        "Authentication",
        "Encryption",
        "Audit Logs",
        "Key Management",
        "SSO Configuration",
    ],
    ProductName.WORKFLOWENGINE.value: [
        "Triggers",
        "Actions",
        "Scheduling",
        "Error Handling",
        "Templates",
    ],
}

CATEGORY_TO_PRODUCT_AREA = {
    ProductName.CLOUDSYNC.value: {
        TicketCategory.INTEGRATION.value: "Integrations",
    },
    ProductName.DATABRIDGE_PRO.value: {
        TicketCategory.INTEGRATION.value: "Connectors",
    },
    ProductName.SECUREVAULT.value: {
        TicketCategory.INTEGRATION.value: "Audit Logs",
    },
}

CATEGORY_RULES = {
    TicketCategory.BILLING.value: {
        "invoice",
        "billing",
        "charged",
        "charge",
        "credit",
        "refund",
        "plan",
        "upgrade",
        "downgrade",
        "renewal",
        "pricing",
        "seat",
        "seats",
    },
    TicketCategory.FEATURE_REQUEST.value: {
        "feature request",
        "roadmap",
        "would love",
        "bulk",
        "request:",
        "enhancement",
        "beta",
    },
    TicketCategory.HOW_TO.value: {
        "how do i",
        "best practice",
        "documentation",
        "guide",
        "how to",
        "can you point us",
    },
    TicketCategory.PERFORMANCE.value: {
        "slow",
        "slowness",
        "latency",
        "timeout",
        "timing out",
        "performance",
        "degradation",
        "stalled",
        "throughput",
    },
    TicketCategory.INTEGRATION.value: {
        "integration",
        "webhook",
        "salesforce",
        "snowflake",
        "hubspot",
        "jira",
        "slack",
        "pagerduty",
        "oauth",
        "scim",
    },
    TicketCategory.ONBOARDING.value: {
        "new users",
        "new joiners",
        "onboarding",
        "setup",
        "provisioning",
        "invite",
        "rollout",
    },
    TicketCategory.DATA_LOSS.value: {
        "missing records",
        "missing data",
        "data loss",
        "corrupted",
        "recover",
        "restore sync",
        "discrepancy",
        "checksum_mismatch",
    },
}

TEAM_BY_CATEGORY = {
    TicketCategory.BILLING.value: "Billing Operations",
    TicketCategory.HOW_TO.value: "Customer Enablement",
    TicketCategory.ONBOARDING.value: "Customer Enablement",
    TicketCategory.BUG.value: "Technical Support Tier 2",
    TicketCategory.PERFORMANCE.value: "Technical Support Tier 2",
    TicketCategory.INTEGRATION.value: "Technical Support Tier 2",
    TicketCategory.FEATURE_REQUEST.value: "Technical Support Tier 2",
    TicketCategory.DATA_LOSS.value: "Incident Response / Escalation",
}


@dataclass(frozen=True)
class TriageHints:
    product: str
    product_area: str
    issue_category: str
    urgency: str
    reasoning: list[str]
    recommended_team: str


def _normalize_ticket_input(raw_ticket: str | dict[str, Any] | TicketInput) -> TicketInput:
    if isinstance(raw_ticket, TicketInput):
        return raw_ticket
    if isinstance(raw_ticket, str):
        return TicketInput(subject="", body=raw_ticket)
    if isinstance(raw_ticket, dict):
        if "body" not in raw_ticket:
            raise ValueError("Ticket input dict must include a 'body' field.")
        return TicketInput.model_validate(raw_ticket)
    raise TypeError("Ticket input must be a string, dict, or TicketInput.")


def _infer_product(ticket_text: str) -> str:
    lowered = ticket_text.lower()

    for product, patterns in PRODUCT_EXACT_PATTERNS.items():
        if any(pattern in lowered for pattern in patterns):
            return product

    for product, keywords in PRODUCT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return product
    return ProductName.UNKNOWN.value


def _infer_product_area(ticket_text: str, product: str, retrieval_results: list[RetrievalResult]) -> str:
    lowered = ticket_text.lower()
    for area in PRODUCT_AREAS.get(product, []):
        if area.lower() in lowered:
            return area

    for result in retrieval_results:
        for area in PRODUCT_AREAS.get(product, []):
            if area.lower() in result.heading.lower() or area.lower() in result.excerpt.lower():
                return area

    if product == ProductName.UNKNOWN.value:
        return "Unknown"
    return PRODUCT_AREAS.get(product, ["General"])[0]


def _infer_category(ticket_text: str, retrieval_results: list[RetrievalResult]) -> str:
    lowered = ticket_text.lower()
    scores = {category: 0 for category in CATEGORY_RULES}

    for category, keywords in CATEGORY_RULES.items():
        for keyword in keywords:
            if keyword in lowered:
                scores[category] += 2

    if "error" in lowered or "failing" in lowered or "unable" in lowered:
        scores[TicketCategory.BUG.value] = scores.get(TicketCategory.BUG.value, 0) + 2

    for result in retrieval_results:
        doc_path = result.doc_path.lower()
        if "billing" in doc_path:
            scores[TicketCategory.BILLING.value] += 2
        if "onboarding" in doc_path or "authentication" in doc_path:
            scores[TicketCategory.ONBOARDING.value] += 1
        if "performance-and-integrations" in doc_path:
            scores[TicketCategory.INTEGRATION.value] += 2
            scores[TicketCategory.PERFORMANCE.value] += 2

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    best_category, best_score = ranked[0]
    if best_score <= 0:
        return TicketCategory.BUG.value

    if best_category == TicketCategory.ONBOARDING.value and ("sso" in lowered or "auth" in lowered):
        return TicketCategory.ONBOARDING.value

    return best_category


def _infer_urgency(ticket_text: str, issue_category: str) -> str:
    lowered = ticket_text.lower()
    score = 0

    if any(term in lowered for term in {"critical", "sev1", "p1", "production down", "business stopped"}):
        score += 6
    if any(term in lowered for term in {"all users", "everyone blocked", "blocked from accessing", "unable to log in"}):
        score += 5
    if any(term in lowered for term in {"data loss", "missing records", "corrupted", "recover the missing", "restore sync"}):
        score += 4
    if any(term in lowered for term in {"not being delivered", "failing", "failed deliveries", "stopped syncing", "not reaching"}):
        score += 3
    if any(term in lowered for term in {"urgent", "urgently", "asap"}):
        score += 2
    if any(term in lowered for term in {"production", "customer-facing", "outage"}):
        score += 2
    if any(term in lowered for term in {"workaround", "manual workaround"}):
        score -= 1
    if any(term in lowered for term in {"feature request", "roadmap", "would love", "upgrade request"}):
        score -= 3

    if issue_category == TicketCategory.DATA_LOSS.value:
        score += 2
    if issue_category == TicketCategory.PERFORMANCE.value:
        score += 1
    if issue_category == TicketCategory.INTEGRATION.value:
        score += 1
    if issue_category == TicketCategory.BILLING.value:
        score -= 1

    if "failed deliveries since:" in lowered:
        try:
            failed_count = int(lowered.split("failed deliveries since:")[1].split()[0].replace(",", ""))
            if failed_count >= 1000:
                score += 3
            elif failed_count >= 100:
                score += 2
            elif failed_count >= 10:
                score += 1
        except (IndexError, ValueError):
            pass

    if score >= 9:
        return UrgencyTier.P1.value
    if score >= 4:
        return UrgencyTier.P2.value
    if score >= 1:
        return UrgencyTier.P3.value
    return UrgencyTier.P4.value


def _recommended_team(issue_category: str, ticket_text: str, urgency: str) -> str:
    lowered = ticket_text.lower()
    if urgency == UrgencyTier.P1.value or issue_category == TicketCategory.DATA_LOSS.value:
        return "Incident Response / Escalation"
    if "sso" in lowered or "saml" in lowered or "authentication" in lowered or "login" in lowered:
        return "Identity / Platform Support"
    return TEAM_BY_CATEGORY.get(issue_category, "Technical Support Tier 2")


def _build_reasoning(
    ticket_text: str,
    product: str,
    product_area: str,
    issue_category: str,
    urgency: str,
    retrieval_results: list[RetrievalResult],
) -> list[str]:
    reasoning: list[str] = []

    reasoning.append(f"Identified product as {product} based on explicit product or feature mentions in the ticket.")
    reasoning.append(f"Assigned product area {product_area} using module keywords and retrieval matches.")

    if issue_category == TicketCategory.INTEGRATION.value:
        reasoning.append("Categorised as an integration issue because the ticket references webhooks, third-party systems, or connector/auth flows.")
    elif issue_category == TicketCategory.ONBOARDING.value:
        reasoning.append("Categorised as onboarding because the issue concerns setup, new users, provisioning, or documentation.")
    elif issue_category == TicketCategory.PERFORMANCE.value:
        reasoning.append("Categorised as performance because the ticket mentions slowness, timeouts, or degraded system behaviour.")
    elif issue_category == TicketCategory.BILLING.value:
        reasoning.append("Categorised as billing because the ticket focuses on invoice, seat count, plan, or pricing questions.")
    elif issue_category == TicketCategory.DATA_LOSS.value:
        reasoning.append("Categorised as data loss because the ticket mentions missing, corrupted, or unrecoverable records.")
    elif issue_category == TicketCategory.FEATURE_REQUEST.value:
        reasoning.append("Categorised as feature request because the user is asking for new functionality rather than a break/fix.")
    else:
        reasoning.append("Categorised as a product bug because the ticket describes an unexpected error or broken behaviour.")

    reasoning.append(f"Assigned urgency {urgency} based on impact language, number of affected users, and whether a workaround exists.")

    if retrieval_results:
        top_result = retrieval_results[0]
        reasoning.append(
            f"Matched a relevant knowledge-base pattern in {top_result.doc_path} under {top_result.heading}."
        )

    return reasoning


def _build_first_response(
    summary: str,
    product: str,
    issue_category: str,
    urgency: str,
    retrieval_results: list[RetrievalResult],
) -> str:
    kb_line = ""
    if retrieval_results:
        kb_line = (
            f" We found a likely relevant internal reference in `{retrieval_results[0].doc_path}` "
            f"and will use that to guide the next checks."
        )

    return (
        f"Thanks for the report. We have triaged this as a {urgency} {issue_category.lower()} issue affecting {product}. "
        f"We are reviewing the symptoms you shared and the likely impact now.{kb_line} "
        f"Our next step is to validate the failure path, confirm whether this matches a known issue, "
        f"and update you with either a workaround or the next action. Summary: {summary}"
    )


def _summarize_ticket(ticket_text: str) -> str:
    return truncate_text(normalize_text(ticket_text), limit=220)


def _maybe_refine_with_llm(
    ticket_text: str,
    retrieval_results: list[RetrievalResult],
    heuristic_response: TriageResponse,
) -> TriageResponse:
    if not settings.enable_llm or not settings.openai_api_key:
        return heuristic_response

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        kb_context = "\n\n".join(
            f"[{result.doc_path}] {result.heading}\n{result.excerpt}"
            for result in retrieval_results[:2]
        )
        response = client.responses.parse(
            model=settings.openai_model,
            temperature=settings.llm_temperature,
            input=[
                {"role": "system", "content": TRIAGE_PROMPT_TEMPLATE},
                {
                    "role": "user",
                    "content": (
                        f"Prompt version: {TRIAGE_PROMPT_ID}\n\n"
                        f"Ticket:\n{ticket_text}\n\n"
                        f"Retrieved KB:\n{kb_context}\n\n"
                        f"Heuristic draft:\n{heuristic_response.model_dump_json(indent=2)}"
                    ),
                },
            ],
            text_format=TriageResponse,
        )
        parsed = response.output_parsed
        if parsed is None:
            return heuristic_response
        return parsed
    except Exception:
        return heuristic_response


def _build_heuristic_triage(ticket_input: TicketInput) -> tuple[TriageResponse, list[RetrievalResult]]:
    ticket_text = merge_subject_body(ticket_input.subject, ticket_input.body)
    retrieval_results = retrieve_relevant_kb(ticket_text=ticket_text, top_k=3)

    product = _infer_product(ticket_text)
    issue_category = _infer_category(ticket_text, retrieval_results)
    product_area = _infer_product_area(ticket_text, product, retrieval_results)
    product_area = CATEGORY_TO_PRODUCT_AREA.get(product, {}).get(issue_category, product_area)
    urgency = _infer_urgency(ticket_text, issue_category)
    team = _recommended_team(issue_category, ticket_text, urgency)
    summary = _summarize_ticket(ticket_text)
    reasoning = _build_reasoning(
        ticket_text=ticket_text,
        product=product,
        product_area=product_area,
        issue_category=issue_category,
        urgency=urgency,
        retrieval_results=retrieval_results,
    )

    response = TriageResponse(
        ticket_summary=summary,
        product=product,
        product_area=product_area,
        issue_category=issue_category,
        urgency=urgency,
        reasoning=reasoning,
        known_issue_match=bool(retrieval_results),
        relevant_doc=retrieval_results[0].doc_path if retrieval_results else None,
        recommended_team=team,
        draft_first_response=clean_multiline_text(
            _build_first_response(
                summary=summary,
                product=product,
                issue_category=issue_category,
                urgency=urgency,
                retrieval_results=retrieval_results,
            )
        ),
    )
    return response, retrieval_results


def triage_ticket(raw_ticket: str | dict[str, Any] | TicketInput) -> TriageResponse:
    ticket_input = _normalize_ticket_input(raw_ticket)
    heuristic_response, retrieval_results = _build_heuristic_triage(ticket_input)
    return _maybe_refine_with_llm(
        ticket_text=merge_subject_body(ticket_input.subject, ticket_input.body),
        retrieval_results=retrieval_results,
        heuristic_response=heuristic_response,
    )
