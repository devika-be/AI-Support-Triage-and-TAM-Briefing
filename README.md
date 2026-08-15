# Production-Grade AI for Technical Support and TAM Teams

Submission for the US Delivery Internship technical task round.

This project builds two internal AI workflows on top of the provided synthetic dataset only:

- Task 1: intelligent ticket triage for support teams
- Task 2: account health summarisation for TAMs

It also includes:

- a lightweight FastAPI service
- a local retrieval layer over the Markdown knowledge base
- a deterministic evaluation harness with saved report output

---

## Repository Overview

```text
.
├── app/
│   ├── account_brief.py
│   ├── api.py
│   ├── config.py
│   ├── data_loader.py
│   ├── models.py
│   ├── retrieval.py
│   ├── risk_rules.py
│   ├── triage.py
│   └── utils.py
├── data/
├── evals/
│   ├── judges.py
│   ├── run_evals.py
│   ├── scorers.py
│   ├── task1_cases.json
│   └── task2_cases.json
├── knowledge-base/
├── reports/
│   └── eval_report.json
├── scripts/
│   ├── sample_account_brief.py
│   ├── sample_retrieval.py
│   └── sample_triage.py
├── .env.example
├── requirements.txt
└── README.md
```

---

## Solution Summary

## Task 1: Intelligent Ticket Triage Agent

The triage pipeline accepts a raw ticket and returns structured support metadata:

- product
- product area
- issue category
- urgency tier `P1-P4`
- reasoning
- known issue / KB match
- recommended responder team
- draft first-response message

Implementation approach:

- deterministic heuristic classification for product, category, urgency, and routing
- local retrieval over the provided Markdown knowledge base
- optional LLM refinement layer that improves wording but does not block output generation
- Pydantic response schema for consistent structured output

## Task 2: TAM Account Health Summariser

The account brief generator accepts an `account_id` and builds a concise TAM-ready briefing using:

- account summary data
- last 90 days of ticket history
- churn and escalation signals from both account metadata and tickets

Output sections:

- executive summary
- open risks and flagged issues
- recommended talking points

Implementation approach:

- deterministic repository lookup using a fixed evaluation reference date
- rule-based risk extraction for stability and explainability
- direct evidence quotes attached to each flagged risk
- optional LLM refinement for summary wording only

## Task 3: Evaluation Harness

The evaluation layer runs fixed cases against both tasks and generates:

- pass/fail per case
- `0-1` quality score per case
- saved JSON report

Current result:

- total cases: `10`
- passed: `10`
- average score: `0.875`

Saved report:

- [reports/eval_report.json](D:\Some Main Projects\Ass_Project_14-08-2026\reports\eval_report.json)

---

## Setup

## 1. Create and activate a virtual environment

### Windows `cmd`

```cmd
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
```

## 2. Install dependencies

```cmd
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 3. Configure environment variables

Create a `.env` file in the repo root using `.env.example` as the template.

Example:

```env
APP_ENV=development
LOG_LEVEL=INFO
ENABLE_LLM=true
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini
LLM_TEMPERATURE=0
LLM_SEED=42
EVAL_REFERENCE_DATE=2026-08-15
DEFAULT_TIMEZONE=UTC
```

Notes:

- the project works without an API key for the deterministic baseline path
- never commit real secrets
- the fixed reference date keeps 90-day ticket filtering stable for evals

---

## Run the API

Start the FastAPI server:

```cmd
python -m uvicorn app.api:app --reload
```

Available endpoints:

- `GET /health`
- `POST /triage`
- `GET /accounts/{account_id}/brief`

Example:

```cmd
curl http://127.0.0.1:8000/health
```

```cmd
curl -X POST http://127.0.0.1:8000/triage ^
  -H "Content-Type: application/json" ^
  -d "{\"subject\":\"Webhook from CloudSync not reaching PagerDuty\",\"body\":\"Our CloudSync webhooks are not being delivered to PagerDuty. We've verified the endpoint is reachable and the secret is correctly configured. Last successful delivery: earlier today. Failed deliveries since: 4731. Webhook logs attached. Please advise.\"}"
```

```cmd
curl http://127.0.0.1:8000/accounts/ACC-3336/brief
```

---

## Sample Local Runs

## Task 1 sample

```cmd
python -m scripts.sample_triage
```

Representative output:

```json
{
  "product": "CloudSync",
  "product_area": "Integrations",
  "issue_category": "Integration",
  "urgency": "P2",
  "recommended_team": "Technical Support Tier 2",
  "relevant_doc": "troubleshooting/performance-and-integrations.md"
}
```

## Task 2 sample

```cmd
python -m scripts.sample_account_brief ACC-3336
```

Representative output:

```json
{
  "account_id": "ACC-3336",
  "company": "Omni Consumer Products",
  "executive_summary": "Omni Consumer Products is a Business account in EU-West...",
  "recommended_talking_points": [
    "Review adoption blockers and agree on a concrete usage recovery plan.",
    "Address the escalation history directly and confirm whether stakeholder concerns are changing."
  ]
}
```

## Retrieval sample

```cmd
python -m scripts.sample_retrieval
```

---

## Evaluation

Run the full evaluation harness:

```cmd
python -m evals.run_evals
```

This will:

- run 5 Task 1 cases
- run 5 Task 2 cases
- include one adversarial case per task
- save a detailed report to [reports/eval_report.json](D:\Some Main Projects\Ass_Project_14-08-2026\reports\eval_report.json)

Current summary:

```json
{
  "total_cases": 10,
  "passed_cases": 10,
  "failed_cases": 0,
  "average_score": 0.875,
  "by_task": {
    "task1": {
      "total": 5,
      "passed": 5,
      "average_score": 0.86
    },
    "task2": {
      "total": 5,
      "passed": 5,
      "average_score": 0.89
    }
  }
}
```

---

## Design Note

## 1. Failure Modes

### Failure mode 1: wrong classification from ambiguous ticket language

Risk:
- tickets may mention symptoms like `sync`, `timeout`, or `login` without clearly identifying the actual product or issue category

Detection:
- monitor disagreement between heuristic classification and retrieved KB grounding
- track low-confidence or `Unknown` product outputs
- review eval regressions on ambiguous and adversarial cases

Mitigation:
- prefer exact product mentions over generic keywords
- keep a fallback `Unknown` product path rather than forcing false certainty
- expand task evals with more ambiguous examples over time

### Failure mode 2: false risk amplification in TAM briefs

Risk:
- account metadata may indicate risk even when recent tickets are low severity, or ticket text may over-index on one recent issue

Detection:
- compare flagged risks against direct evidence coverage
- inspect how often high-severity flags come from account metadata only vs ticket evidence
- review whether the same accounts repeatedly trigger the same top risk without fresh evidence

Mitigation:
- separate account-level and ticket-level risk rules
- attach an evidence quote to every flag
- deduplicate repeated signals and sort them deterministically

### Failure mode 3: retrieval mismatch returns the wrong KB article

Risk:
- a generic troubleshooting document can outrank a more precise product section

Detection:
- track the top matched KB doc for known test cases
- inspect retrieval misses in eval failures
- log error-code and keyword matches used in ranking

Mitigation:
- combine lexical overlap with product-specific and category-specific boosts
- prefer exact error-code matches and exact product mentions
- keep retrieval local and inspectable instead of hiding ranking in a black-box external system

## 2. Latency vs Quality Trade-off

One concrete trade-off was using rule-based classification and scoring before optional LLM refinement.

Why:
- deterministic heuristics are much faster and more stable for evals
- they also provide a safe fallback if the LLM call fails or is unavailable

Cost:
- the baseline output can be less fluent than a full prompt-only solution
- some edge cases need manual scoring tweaks instead of being resolved purely by the model

If latency were the hard constraint:
- I would disable LLM refinement by default
- rely fully on local heuristics and retrieval
- pre-load the KB and datasets at application startup to reduce repeated disk reads

## 3. Data Sensitivity

Ticket and account data may contain PII, even in synthetic form here. The design tries to minimise leakage risk:

- the retrieval corpus is local and uses only the provided files
- no external scraping, enrichment, or live customer data is used
- the code supports a deterministic path that works without calling an external API
- the LLM path can be disabled with `ENABLE_LLM=false`
- secrets are read from environment variables rather than source files

In a production deployment, I would also:

- redact emails, names, tokens, and account identifiers before external model calls
- route sensitive workloads through an approved enterprise endpoint
- log only hashed identifiers or minimal telemetry

## 4. Scaling to 10x Ticket Volume

At 10x volume, the first bottlenecks would be:

- repeated disk reads for tickets, accounts, and KB documents
- repeated KB chunking during retrieval
- synchronous request-time inference for every request

What would break first:
- latency would rise before correctness breaks
- concurrent API usage would amplify repeated file loading and retrieval work

How I would scale it:

- cache datasets and KB chunks in memory at startup
- precompute retrieval chunks once instead of per request
- separate online inference from offline evaluation jobs
- add request-level tracing and timing around retrieval and summarisation steps
- batch or queue non-urgent summarisation workloads

This architecture should still work at 10x volume, but it needs caching and request lifecycle optimisation before being considered production-ready at that scale.

---

## Assumptions and Constraints

- only the provided synthetic dataset and knowledge-base are used
- some starter labels are intentionally noisy, so heuristics do not blindly trust dataset labels as ground truth
- the reference date for recent-ticket analysis is fixed to `2026-08-15` for deterministic evaluation

---

## Submission Checklist Mapping

- Task 1 implementation: complete
- Task 2 implementation: complete
- Task 3 evaluation harness: complete
- Design note: included in this README
- Setup instructions: included
- Sample commands: included
- Eval report file: included at [reports/eval_report.json](D:\Some Main Projects\Ass_Project_14-08-2026\reports\eval_report.json)
- `.env.example`: included

---


