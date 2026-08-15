from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from app.data_loader import load_kb_documents
from app.models import KnowledgeBaseChunk, KnowledgeBaseDocument, TicketPayload
from app.utils import extract_error_codes, normalize_text, truncate_text


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-/+\.]*", re.IGNORECASE)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "hi",
    "how",
    "i",
    "in",
    "is",
    "it",
    "last",
    "my",
    "new",
    "not",
    "of",
    "on",
    "or",
    "our",
    "please",
    "team",
    "the",
    "this",
    "to",
    "up",
    "we",
    "with",
    "you",
    "your",
}

PRODUCT_ALIASES = {
    "databridge pro": {"databridge", "databridge-pro", "databridge", "connectors", "pipeline"},
    "cloudsync": {"cloudsync", "sync", "sso_group_not_found", "bandwidth", "permissions"},
    "analyticshub": {"analyticshub", "dashboard", "alerts", "reports", "exports"},
    "securevault": {"securevault", "vault", "keys", "saml", "audit"},
    "workflowengine": {"workflowengine", "workflow", "cron", "trigger", "actions"},
}

CATEGORY_KEYWORDS = {
    "billing": {"invoice", "billing", "credit", "charge", "seats", "plan", "upgrade", "downgrade"},
    "onboarding": {"onboarding", "new users", "new joiners", "provisioning", "invite", "setup"},
    "authentication": {"sso", "saml", "auth", "authentication", "login", "group_not_mapped"},
    "performance": {"slow", "slowness", "timeout", "latency", "performance", "stalled"},
    "integration": {"integration", "webhook", "salesforce", "snowflake", "hubspot", "jira", "pagerduty"},
}

DOC_HINTS = {
    "troubleshooting/authentication-sso.md": {
        "sso",
        "saml",
        "authentication",
        "login",
        "group_not_mapped",
        "sso_group_not_found",
        "idp",
    },
    "troubleshooting/performance-and-integrations.md": {
        "webhook",
        "pagerduty",
        "salesforce",
        "snowflake",
        "hubspot",
        "jira",
        "integration",
        "timeout",
        "performance",
        "dependency_unavailable",
        "invalid_configuration",
    },
    "billing/billing-and-plans.md": {
        "invoice",
        "billing",
        "credit",
        "charge",
        "seats",
        "upgrade",
        "downgrade",
    },
    "onboarding/onboarding-guide.md": {
        "onboarding",
        "new users",
        "new joiners",
        "invite",
        "provisioning",
        "training",
    },
}


@dataclass(frozen=True)
class RetrievalResult:
    doc_path: str
    title: str
    heading: str
    score: float
    excerpt: str
    matched_error_codes: list[str]


def _tokenize(text: str) -> list[str]:
    tokens = [token.lower() for token in TOKEN_RE.findall(text)]
    return [token for token in tokens if token not in STOPWORDS]


def _heading_text(heading_path: list[str]) -> str:
    return " > ".join(heading_path)


def chunk_markdown_document(document: KnowledgeBaseDocument) -> list[KnowledgeBaseChunk]:
    chunks: list[KnowledgeBaseChunk] = []
    current_headings: list[str] = []
    current_lines: list[str] = []
    chunk_index = 0

    def flush_chunk() -> None:
        nonlocal chunk_index, current_lines
        content = "\n".join(current_lines).strip()
        if not content:
            current_lines = []
            return
        chunks.append(
            KnowledgeBaseChunk(
                doc_path=document.path,
                title=document.title,
                heading_path=current_headings.copy(),
                content=content,
                chunk_index=chunk_index,
            )
        )
        chunk_index += 1
        current_lines = []

    for raw_line in document.content.splitlines():
        line = raw_line.rstrip()
        if line.strip() == "---":
            flush_chunk()
            continue

        heading_match = HEADING_RE.match(line.strip())
        if heading_match:
            flush_chunk()
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()
            current_headings[:] = current_headings[: level - 1]
            current_headings.append(heading)
            current_lines.append(line)
            continue

        current_lines.append(line)

    flush_chunk()
    return chunks


def build_kb_chunks(documents: Iterable[KnowledgeBaseDocument] | None = None) -> list[KnowledgeBaseChunk]:
    kb_documents = list(documents) if documents is not None else load_kb_documents()
    chunks: list[KnowledgeBaseChunk] = []
    for document in kb_documents:
        chunks.extend(chunk_markdown_document(document))
    return chunks


def _collect_query_terms(ticket_text: str, product: str | None = None, product_area: str | None = None) -> set[str]:
    terms = set(_tokenize(ticket_text))
    for code in extract_error_codes(ticket_text):
        terms.add(code.lower())

    if product:
        product_key = product.lower()
        terms.update(_tokenize(product_key))
        terms.update(PRODUCT_ALIASES.get(product_key, set()))

    if product_area:
        terms.update(_tokenize(product_area))

    lowered_text = ticket_text.lower()
    for keyword_group in CATEGORY_KEYWORDS.values():
        if any(keyword in lowered_text for keyword in keyword_group):
            terms.update(keyword_group)

    return terms


def _score_chunk(
    chunk: KnowledgeBaseChunk,
    query_terms: set[str],
    error_codes: list[str],
    product: str | None = None,
    product_area: str | None = None,
) -> tuple[float, list[str]]:
    chunk_text = " ".join(
        [
            chunk.title,
            _heading_text(chunk.heading_path),
            chunk.content,
        ]
    ).lower()
    chunk_tokens = set(_tokenize(chunk_text))

    overlap = query_terms.intersection(chunk_tokens)
    score = float(len(overlap))

    matched_codes = [code for code in error_codes if code.lower() in chunk_text]
    score += 5.0 * len(matched_codes)

    if product and product.lower() in chunk_text:
        score += 4.0

    if product_area and product_area.lower() in chunk_text:
        score += 2.0

    if any("troubleshooting" in heading.lower() for heading in chunk.heading_path):
        score += 0.5

    doc_hints = DOC_HINTS.get(chunk.doc_path, set())
    for hint in doc_hints:
        if hint in chunk_text and hint in query_terms:
            score += 2.0

    if "webhook" in query_terms and "webhook" in chunk_text:
        score += 3.0

    if "integration" in query_terms and "integration" in chunk_text:
        score += 2.0

    if "pagerduty" in query_terms and "pagerduty" in chunk_text:
        score += 3.0

    if "snowflake" in query_terms and "snowflake" in chunk_text:
        score += 3.0

    if "salesforce" in query_terms and "salesforce" in chunk_text:
        score += 3.0

    if chunk.doc_path == "troubleshooting/performance-and-integrations.md":
        integration_terms = {"webhook", "integration", "pagerduty", "snowflake", "salesforce", "hubspot", "jira"}
        score += 1.5 * len(query_terms.intersection(integration_terms))

    if chunk.doc_path == "troubleshooting/authentication-sso.md":
        auth_terms = {"sso", "saml", "authentication", "login", "group_not_mapped", "sso_group_not_found", "idp"}
        score += 1.5 * len(query_terms.intersection(auth_terms))

    return score, matched_codes


def retrieve_relevant_kb(
    ticket_text: str,
    product: str | None = None,
    product_area: str | None = None,
    documents: Iterable[KnowledgeBaseDocument] | None = None,
    top_k: int = 3,
) -> list[RetrievalResult]:
    chunks = build_kb_chunks(documents)
    error_codes = extract_error_codes(ticket_text)
    query_terms = _collect_query_terms(ticket_text, product=product, product_area=product_area)

    scored_results: list[RetrievalResult] = []
    for chunk in chunks:
        score, matched_codes = _score_chunk(
            chunk,
            query_terms=query_terms,
            error_codes=error_codes,
            product=product,
            product_area=product_area,
        )
        if score <= 0:
            continue

        scored_results.append(
            RetrievalResult(
                doc_path=chunk.doc_path,
                title=chunk.title,
                heading=_heading_text(chunk.heading_path) or chunk.title,
                score=score,
                excerpt=truncate_text(normalize_text(chunk.content), limit=280),
                matched_error_codes=matched_codes,
            )
        )

    scored_results.sort(key=lambda item: (-item.score, item.doc_path, item.heading))
    return scored_results[:top_k]


def retrieve_for_ticket(
    ticket: TicketPayload,
    documents: Iterable[KnowledgeBaseDocument] | None = None,
    top_k: int = 3,
) -> list[RetrievalResult]:
    ticket_text = "\n\n".join(
        part for part in [ticket.subject, ticket.body] if part
    )
    return retrieve_relevant_kb(
        ticket_text=ticket_text,
        product=str(ticket.product),
        product_area=ticket.product_area,
        documents=documents,
        top_k=top_k,
    )
