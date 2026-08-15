from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.account_brief import build_account_brief
from app.config import REPORTS_DIR, ROOT_DIR
from app.triage import triage_ticket
from evals.scorers import score_task1_case, score_task2_case


EVALS_DIR = ROOT_DIR / "evals"
TASK1_CASES_PATH = EVALS_DIR / "task1_cases.json"
TASK2_CASES_PATH = EVALS_DIR / "task2_cases.json"
REPORT_PATH = REPORTS_DIR / "eval_report.json"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _run_task1_case(case: dict[str, Any]) -> dict[str, Any]:
    output = triage_ticket(case["input"]).model_dump()
    scoring = score_task1_case(case, output)
    return {
        "id": case["id"],
        "task": "task1",
        "description": case["description"],
        "passed": scoring["passed"],
        "score": scoring["score"],
        "checks": scoring["checks"],
        "output": output,
    }


def _run_task2_case(case: dict[str, Any]) -> dict[str, Any]:
    try:
        output = build_account_brief(case["account_id"]).model_dump()
        scoring = score_task2_case(case, output=output)
        return {
            "id": case["id"],
            "task": "task2",
            "description": case["description"],
            "passed": scoring["passed"],
            "score": scoring["score"],
            "checks": scoring["checks"],
            "output": output,
        }
    except Exception as exc:
        scoring = score_task2_case(case, error=str(exc))
        return {
            "id": case["id"],
            "task": "task2",
            "description": case["description"],
            "passed": scoring["passed"],
            "score": scoring["score"],
            "checks": scoring["checks"],
            "error": str(exc),
        }


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    average_score = round(sum(result["score"] for result in results) / total, 3) if total else 0.0
    by_task: dict[str, dict[str, Any]] = {}

    for task_name in {"task1", "task2"}:
        task_results = [result for result in results if result["task"] == task_name]
        if not task_results:
            continue
        by_task[task_name] = {
            "total": len(task_results),
            "passed": sum(1 for result in task_results if result["passed"]),
            "average_score": round(sum(result["score"] for result in task_results) / len(task_results), 3),
        }

    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "average_score": average_score,
        "by_task": by_task,
    }


def run_evaluations() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    task1_cases = _load_cases(TASK1_CASES_PATH)
    task2_cases = _load_cases(TASK2_CASES_PATH)

    results = []
    results.extend(_run_task1_case(case) for case in task1_cases)
    results.extend(_run_task2_case(case) for case in task2_cases)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "summary": _aggregate(results),
    }

    with REPORT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    return report


def main() -> None:
    report = run_evaluations()
    print(json.dumps(report["summary"], indent=2))
    print(f"\nSaved report to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
