# Prompt Changelog

## 2026-08-15

### Added

- `TRIAGE_V1` as the initial ticket triage prompt
- `ACCOUNT_BRIEF_V1` as the initial TAM account brief prompt

### Notes

- both prompts are designed as optional refinement layers on top of deterministic baseline logic
- CI runs with `ENABLE_LLM=false`, so prompt changes do not affect the baseline regression path unless explicitly enabled
