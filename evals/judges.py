from __future__ import annotations

from typing import Any


def contains_acknowledgement_and_next_step(text: str) -> bool:
    lowered = text.lower()
    has_ack = any(token in lowered for token in {"thanks", "thank you", "we have triaged", "we are reviewing"})
    has_next_step = any(
        token in lowered
        for token in {"next step", "we will", "update you", "validate", "confirm whether this matches"}
    )
    return has_ack and has_next_step


def reasoning_quality_score(reasoning: list[str]) -> float:
    if not reasoning:
        return 0.0
    score = 0.0
    if len(reasoning) >= 3:
        score += 0.4
    if any("product" in item.lower() for item in reasoning):
        score += 0.2
    if any("urgency" in item.lower() for item in reasoning):
        score += 0.2
    if any("knowledge-base" in item.lower() or "matched" in item.lower() for item in reasoning):
        score += 0.2
    return min(score, 1.0)


def has_ticket_backed_flag(flags: list[dict[str, Any]]) -> bool:
    return any(flag.get("source_ticket_id") and flag.get("evidence_quote") for flag in flags)
