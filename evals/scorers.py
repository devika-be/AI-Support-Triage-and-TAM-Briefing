from __future__ import annotations

from typing import Any

from evals.judges import contains_acknowledgement_and_next_step, has_ticket_backed_flag, reasoning_quality_score


def _score_boolean(check: bool, weight: float) -> float:
    return weight if check else 0.0


def score_task1_case(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "name": "product_match",
            "passed": output.get("product") == expected["product"],
            "weight": 0.2,
        }
    )
    checks.append(
        {
            "name": "category_match",
            "passed": output.get("issue_category") == expected["issue_category"],
            "weight": 0.2,
        }
    )
    checks.append(
        {
            "name": "urgency_match",
            "passed": output.get("urgency") == expected["urgency"],
            "weight": 0.15,
        }
    )
    checks.append(
        {
            "name": "team_match",
            "passed": output.get("recommended_team") == expected["recommended_team"],
            "weight": 0.15,
        }
    )
    checks.append(
        {
            "name": "relevant_doc_match",
            "passed": expected["relevant_doc_contains"] in (output.get("relevant_doc") or ""),
            "weight": 0.1,
        }
    )
    checks.append(
        {
            "name": "first_response_quality",
            "passed": contains_acknowledgement_and_next_step(output.get("draft_first_response", "")),
            "weight": 0.1,
        }
    )
    checks.append(
        {
            "name": "reasoning_quality",
            "passed": reasoning_quality_score(output.get("reasoning", [])) >= 0.8,
            "weight": 0.1,
        }
    )

    score = round(sum(_score_boolean(check["passed"], check["weight"]) for check in checks), 3)
    passed = score >= 0.75
    return {"score": score, "passed": passed, "checks": checks}


def score_task2_case(case: dict[str, Any], output: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
    expected = case["expected"]
    checks: list[dict[str, Any]] = []

    if "error_contains" in expected:
        passed = error is not None and expected["error_contains"] in error
        score = 1.0 if passed else 0.0
        checks.append({"name": "expected_error", "passed": passed, "weight": 1.0})
        return {"score": score, "passed": passed, "checks": checks}

    if output is None:
        return {
            "score": 0.0,
            "passed": False,
            "checks": [{"name": "output_present", "passed": False, "weight": 1.0}],
        }

    summary = output.get("executive_summary", "")
    flags = output.get("open_risks_and_flagged_issues", [])
    talking_points = output.get("recommended_talking_points", [])

    checks.append(
        {
            "name": "company_match",
            "passed": output.get("company") == expected["company"],
            "weight": 0.15,
        }
    )
    checks.append(
        {
            "name": "three_section_structure",
            "passed": bool(summary) and isinstance(flags, list) and isinstance(talking_points, list),
            "weight": 0.2,
        }
    )
    checks.append(
        {
            "name": "minimum_risk_flags",
            "passed": len(flags) >= expected.get("min_risk_flags", 0),
            "weight": 0.2,
        }
    )

    required_titles = expected.get("must_include_flag_titles", [])
    checks.append(
        {
            "name": "required_flag_titles",
            "passed": all(any(flag.get("title") == title for flag in flags) for title in required_titles),
            "weight": 0.2,
        }
    )

    summary_terms = expected.get("must_contain_summary", [])
    checks.append(
        {
            "name": "summary_contains_required_terms",
            "passed": all(term in summary for term in summary_terms),
            "weight": 0.1,
        }
    )

    if expected.get("must_include_ticket_quote"):
        checks.append(
            {
                "name": "ticket_backed_quote_present",
                "passed": has_ticket_backed_flag(flags),
                "weight": 0.1,
            }
        )

    if expected.get("must_have_talking_points"):
        checks.append(
            {
                "name": "talking_points_present",
                "passed": len(talking_points) > 0,
                "weight": 0.05,
            }
        )

    score = round(sum(_score_boolean(check["passed"], check["weight"]) for check in checks), 3)
    passed = score >= 0.75
    return {"score": score, "passed": passed, "checks": checks}
