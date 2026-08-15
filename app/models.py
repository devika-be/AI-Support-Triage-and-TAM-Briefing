from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ProductName(str, Enum):
    DATABRIDGE_PRO = "DataBridge Pro"
    CLOUDSYNC = "CloudSync"
    ANALYTICSHUB = "AnalyticsHub"
    SECUREVAULT = "SecureVault"
    WORKFLOWENGINE = "WorkflowEngine"
    UNKNOWN = "Unknown"


class TicketCategory(str, Enum):
    BUG = "Bug"
    FEATURE_REQUEST = "Feature Request"
    HOW_TO = "How-To"
    PERFORMANCE = "Performance"
    BILLING = "Billing"
    INTEGRATION = "Integration"
    ONBOARDING = "Onboarding"
    DATA_LOSS = "Data Loss"
    UNKNOWN = "Unknown"


class UrgencyTier(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    UNKNOWN = "Unknown"


class TicketStatus(str, Enum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    PENDING_CUSTOMER = "Pending Customer"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


class PlanTier(str, Enum):
    STARTER = "Starter"
    PROFESSIONAL = "Professional"
    BUSINESS = "Business"
    ENTERPRISE = "Enterprise"


class SupportChannel(str, Enum):
    EMAIL = "email"
    PORTAL = "portal"
    CHAT = "chat"
    PHONE = "phone"


class HealthStatus(str, Enum):
    HEALTHY = "Healthy"
    AT_RISK = "At Risk"
    CHURNING = "Churning"
    NEW = "New"


class UsageTrend(str, Enum):
    INCREASING = "Increasing"
    STABLE = "Stable"
    DECLINING = "Declining"
    INACTIVE = "Inactive"


class BaseSchema(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)


class TicketInput(BaseSchema):
    subject: str = Field(default="", description="Ticket subject line.")
    body: str = Field(..., min_length=1, description="Ticket body text.")


class TicketPayload(BaseSchema):
    ticket_id: str
    account_id: str | None = None
    company: str | None = None
    subject: str
    body: str
    product: ProductName | str
    product_area: str
    category: TicketCategory | str
    urgency: UrgencyTier | str
    status: TicketStatus | str
    plan_tier: PlanTier | str
    assigned_agent: str | None = None
    created_at: datetime
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)
    channel: SupportChannel | str
    satisfaction_score: int | None = None


class PrimaryContact(BaseSchema):
    name: str
    title: str


class AccountPayload(BaseSchema):
    account_id: str
    company: str
    tam: str
    plan_tier: PlanTier | str
    arr_usd: int
    seats_licensed: int
    seats_active: int
    products: list[ProductName | str] = Field(default_factory=list)
    health_status: HealthStatus | str
    usage_trend: UsageTrend | str
    open_tickets: int
    p1_tickets_last_30d: int
    customer_since: str | None = None
    renewal_date: str
    last_qbr_date: str
    primary_contact: PrimaryContact
    escalation_notes: list[str] = Field(default_factory=list)
    nps_score: int | None = None
    last_login_days_ago: int | None = None
    integrations_active: list[str] = Field(default_factory=list)
    region: str
    industry: str


class KnowledgeBaseDocument(BaseSchema):
    path: str
    category: str
    title: str
    content: str


class KnowledgeBaseChunk(BaseSchema):
    doc_path: str
    title: str
    heading_path: list[str] = Field(default_factory=list)
    content: str
    chunk_index: int


class TriageResponse(BaseSchema):
    ticket_summary: str
    product: ProductName | str
    product_area: str
    issue_category: TicketCategory | str
    urgency: UrgencyTier | str
    reasoning: list[str] = Field(default_factory=list)
    known_issue_match: bool
    relevant_doc: str | None = None
    recommended_team: str
    draft_first_response: str


class RiskFlag(BaseSchema):
    title: str
    severity: str
    rationale: str
    evidence_quote: str
    source_ticket_id: str | None = None


class AccountBriefResponse(BaseSchema):
    account_id: str
    company: str
    executive_summary: str
    open_risks_and_flagged_issues: list[RiskFlag] = Field(default_factory=list)
    recommended_talking_points: list[str] = Field(default_factory=list)

