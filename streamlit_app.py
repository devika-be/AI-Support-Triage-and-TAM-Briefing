from __future__ import annotations

import json
import time
from typing import Iterable

import streamlit as st

from app.account_brief import build_account_brief
from app.triage import triage_ticket


st.set_page_config(
    page_title="AI Support Operations Demo",
    page_icon=":clipboard:",
    layout="wide",
)


CUSTOM_CSS = """
<style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }
    .hero {
        padding: 1.25rem 1.5rem;
        border-radius: 18px;
        background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 55%, #93c5fd 100%);
        color: white;
        margin-bottom: 1.25rem;
        box-shadow: 0 16px 40px rgba(15, 23, 42, 0.18);
    }
    .hero h1 {
        margin: 0 0 0.4rem 0;
        font-size: 2.2rem;
        line-height: 1.1;
    }
    .hero p {
        margin: 0;
        font-size: 1rem;
        opacity: 0.92;
    }
    .panel {
        background: #f8fafc;
        border: 1px solid #dbe4f0;
        border-radius: 16px;
        padding: 1rem 1.1rem;
        margin-bottom: 1rem;
    }
    .panel h3 {
        margin-top: 0;
        margin-bottom: 0.5rem;
    }
    .doc-chip {
        display: inline-block;
        background: #dbeafe;
        color: #1e3a8a;
        border-radius: 999px;
        padding: 0.35rem 0.7rem;
        font-size: 0.9rem;
        font-weight: 600;
        margin-top: 0.4rem;
    }
    .response-box {
        background: white;
        border-left: 4px solid #2563eb;
        border-radius: 10px;
        padding: 0.9rem 1rem;
        line-height: 1.5;
        box-shadow: inset 0 0 0 1px #dbeafe;
    }
    .risk-critical, .risk-high, .risk-medium, .risk-low {
        border-radius: 14px;
        padding: 0.9rem 1rem;
        margin-bottom: 0.75rem;
        border: 1px solid transparent;
    }
    .risk-critical {
        background: #fef2f2;
        border-color: #fecaca;
    }
    .risk-high {
        background: #fff7ed;
        border-color: #fed7aa;
    }
    .risk-medium {
        background: #fffbeb;
        border-color: #fde68a;
    }
    .risk-low {
        background: #f0fdf4;
        border-color: #bbf7d0;
    }
    .eyebrow {
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.76rem;
        font-weight: 700;
        opacity: 0.8;
        margin-bottom: 0.4rem;
    }
</style>
"""


def stream_text(text: str, delay: float = 0.006) -> Iterable[str]:
    words = text.split()
    for word in words:
        yield word + " "
        time.sleep(delay)


def render_header() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="hero">
            <div class="eyebrow">AI Support Operations Demo</div>
            <h1>Technical Support triage and TAM account briefing</h1>
            <p>Production-style internal tooling built only on the provided synthetic ticket, account, and knowledge-base dataset.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_classification_metrics(result) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Product", result.product)
    col2.metric("Category", result.issue_category)
    col3.metric("Urgency", result.urgency)
    col4.metric("Team", result.recommended_team)
    st.caption(f"Product area: {result.product_area}")
    if result.relevant_doc:
        st.markdown(
            f'<div class="doc-chip">KB match: {result.relevant_doc}</div>',
            unsafe_allow_html=True,
        )


def render_triage_tab() -> None:
    st.caption("For support agents: classify incoming tickets, route ownership, and generate a grounded first response.")

    with st.form("triage_form"):
        subject = st.text_input(
            "Subject",
            value="Webhook from CloudSync not reaching PagerDuty",
        )
        body = st.text_area(
            "Body",
            value=(
                "Our CloudSync webhooks are not being delivered to PagerDuty. "
                "We've verified the endpoint is reachable and the secret is correctly configured.\n\n"
                "Last successful delivery: earlier today\n"
                "Failed deliveries since: 4731\n\n"
                "Webhook logs attached. Please advise."
            ),
            height=220,
        )
        submitted = st.form_submit_button("Run Triage", type="primary")

    if not submitted:
        return

    if not body.strip():
        st.error("Ticket body is required.")
        return

    with st.spinner("Classifying ticket and retrieving knowledge-base context..."):
        result = triage_ticket({"subject": subject, "body": body})

    top_left, top_right = st.columns([0.9, 1.1])

    with top_left:
        st.markdown('<div class="panel"><h3>Classification</h3></div>', unsafe_allow_html=True)
        render_classification_metrics(result)

        st.markdown('<div class="panel"><h3>Reasoning</h3></div>', unsafe_allow_html=True)
        for item in result.reasoning:
            st.write(f"- {item}")

    with top_right:
        st.markdown('<div class="panel"><h3>Draft First Response</h3></div>', unsafe_allow_html=True)
        response_container = st.empty()
        with response_container.container():
            st.markdown('<div class="response-box">', unsafe_allow_html=True)
            streamed = st.write_stream(stream_text(result.draft_first_response))
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="panel"><h3>Ticket Summary</h3></div>', unsafe_allow_html=True)
        st.write(result.ticket_summary)

    with st.expander("Structured Output JSON"):
        st.code(json.dumps(result.model_dump(), indent=2), language="json")


def risk_css_class(severity: str) -> str:
    severity = severity.lower()
    if severity in {"critical", "high", "medium", "low"}:
        return f"risk-{severity}"
    return "risk-medium"


def render_account_tab() -> None:
    st.caption("For TAMs: generate a concise account brief with evidence-backed risks and suggested talking points.")

    with st.form("account_form"):
        account_id = st.text_input("Account ID", value="ACC-3336")
        submitted = st.form_submit_button("Generate Brief", type="primary")

    if not submitted:
        return

    if not account_id.strip():
        st.error("Account ID is required.")
        return

    try:
        with st.spinner("Reviewing account health, recent tickets, and escalation signals..."):
            result = build_account_brief(account_id.strip())
    except Exception as exc:
        st.error(str(exc))
        return

    st.markdown('<div class="panel"><h3>Executive Summary</h3></div>', unsafe_allow_html=True)
    st.write_stream(stream_text(result.executive_summary, delay=0.005))

    left, right = st.columns([1.25, 0.75])

    with left:
        st.markdown('<div class="panel"><h3>Open Risks & Flagged Issues</h3></div>', unsafe_allow_html=True)
        for flag in result.open_risks_and_flagged_issues:
            st.markdown(
                (
                    f'<div class="{risk_css_class(flag.severity)}">'
                    f"<strong>{flag.title}</strong> [{flag.severity.upper()}]<br/>"
                    f"{flag.rationale}<br/><br/>"
                    f"<em>Evidence:</em> {flag.evidence_quote}"
                    f"{'<br/><em>Source ticket:</em> ' + flag.source_ticket_id if flag.source_ticket_id else ''}"
                    f"</div>"
                ),
                unsafe_allow_html=True,
            )

    with right:
        st.markdown('<div class="panel"><h3>Recommended Talking Points</h3></div>', unsafe_allow_html=True)
        for point in result.recommended_talking_points:
            st.write(f"- {point}")

    with st.expander("Structured Output JSON"):
        st.code(json.dumps(result.model_dump(), indent=2), language="json")


def main() -> None:
    render_header()
    tab_triage, tab_account = st.tabs(["Ticket Triage", "Account Brief"])
    with tab_triage:
        render_triage_tab()
    with tab_account:
        render_account_tab()


if __name__ == "__main__":
    main()
