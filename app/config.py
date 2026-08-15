from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
KNOWLEDGE_BASE_DIR = ROOT_DIR / "knowledge-base"
REPORTS_DIR = ROOT_DIR / "reports"

load_dotenv(ROOT_DIR / ".env")


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or default


def _get_bool(name: str, default: bool) -> bool:
    value = _get_env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = _get_env(name)
    if value is None:
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    app_name: str = "support-ai-assistant"
    app_env: str = _get_env("APP_ENV", "development") or "development"
    openai_api_key: str | None = _get_env("OPENAI_API_KEY")
    openai_model: str = _get_env("OPENAI_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini"
    log_level: str = _get_env("LOG_LEVEL", "INFO") or "INFO"
    eval_reference_date: str = _get_env("EVAL_REFERENCE_DATE", "2026-08-15") or "2026-08-15"
    default_timezone: str = _get_env("DEFAULT_TIMEZONE", "UTC") or "UTC"
    llm_temperature: float = float(_get_env("LLM_TEMPERATURE", "0") or "0")
    llm_seed: int = _get_int("LLM_SEED", 42)
    enable_llm: bool = _get_bool("ENABLE_LLM", True)


settings = Settings()

