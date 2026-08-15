from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.account_brief import build_account_brief
from app.config import settings
from app.models import AccountBriefResponse, TicketInput, TriageResponse
from app.triage import triage_ticket


app = FastAPI(
    title="US Delivery Internship AI Support Assistant",
    version="0.1.0",
    description="LLM-assisted triage and TAM account briefing service built on the provided mock dataset.",
)


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "environment": settings.app_env,
        "llm_enabled": settings.enable_llm,
    }


@app.post("/triage", response_model=TriageResponse)
def triage(ticket: TicketInput) -> TriageResponse:
    try:
        return triage_ticket(ticket)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Triage failed: {exc}") from exc


@app.get("/accounts/{account_id}/brief", response_model=AccountBriefResponse)
def account_brief(account_id: str) -> AccountBriefResponse:
    try:
        return build_account_brief(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Account brief generation failed: {exc}") from exc
