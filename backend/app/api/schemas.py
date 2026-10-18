from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Sentiment, TagType, Urgency

GITHUB_REPO_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$"
AREA_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"
WORKSPACE_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{1,63}$"
# Deliberately simple: the point is to catch typos, not to police what an address may contain.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class SignUp(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=320, examples=["you@example.com"])
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)


class SignIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


class TokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    email: str
    name: str


class WorkspaceMembership(BaseModel):
    """A workspace someone belongs to, and what they may do in it."""

    slug: str
    name: str
    role: str


class MemberRead(BaseModel):
    """A person who belongs to a workspace."""

    email: str
    name: str
    role: str


class UserRead(BaseModel):
    id: int
    email: str
    name: str
    workspaces: list[WorkspaceMembership]


class WorkspaceCreate(BaseModel):
    slug: str = Field(pattern=WORKSPACE_SLUG_PATTERN, examples=["acme"])
    name: str = Field(min_length=1, max_length=200)


class WorkspaceRead(BaseModel):
    slug: str
    name: str
    is_public: bool
    role: str


class MemberInvite(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=320)
    # Ownership is not handed over through an invite.
    role: Literal["admin", "member", "viewer"] = "member"


class GithubSourceCreate(BaseModel):
    repo: str = Field(pattern=GITHUB_REPO_PATTERN, examples=["microsoft/vscode"])
    backfill_days: int = Field(default=30, ge=1, le=365)
    max_items: int = Field(default=2000, ge=1, le=20_000)


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    name: str
    config: dict[str, Any]
    last_synced_at: datetime | None
    created_at: datetime


class ProductAreaIn(BaseModel):
    slug: str = Field(pattern=AREA_SLUG_PATTERN, examples=["terminal"])
    name: str = Field(min_length=1, max_length=100, examples=["Terminal"])
    description: str = Field(default="", max_length=500, examples=["Integrated terminal, shells"])

    @field_validator("slug")
    @classmethod
    def slug_is_not_reserved(cls, value: str) -> str:
        if value == "other":
            raise ValueError('"other" is reserved for feedback that fits no area')
        return value


class ProductAreaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    description: str


class TaggingStatus(BaseModel):
    total_items: int
    maintainer_items: int
    tagged_items: int
    reviewed_by_human: int
    pending_items: int
    by_type: dict[str, int]


class ItemTagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str
    area: str
    sentiment: str
    urgency: str
    confidence: float
    summary: str
    reviewed_by_human: bool


class FeedbackItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    url: str
    title: str
    state: str
    state_reason: str | None
    labels: list[str]
    comments_count: int
    reactions_count: int
    author_is_maintainer: bool
    external_created_at: datetime
    tag: ItemTagRead | None


class FeedbackItemDetail(FeedbackItemRead):
    body_clean: str


class ItemPage(BaseModel):
    total: int
    items: list[FeedbackItemRead]


class ItemFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(default=None, max_length=200)
    type: TagType | None = None
    area: str | None = Field(default=None, max_length=64)
    sentiment: Sentiment | None = None
    urgency: Urgency | None = None
    state: Literal["open", "closed"] | None = None
    untagged: bool = False
    include_maintainer: bool = False
    sort: Literal["newest", "oldest", "most_reactions"] = "newest"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ItemTagUpdate(BaseModel):
    """A person's correction; only the given fields change."""

    type: TagType | None = None
    area: str | None = Field(default=None, max_length=64)
    sentiment: Sentiment | None = None
    urgency: Urgency | None = None

    @model_validator(mode="after")
    def at_least_one_change(self) -> "ItemTagUpdate":
        if not self.model_dump(exclude_none=True):
            raise ValueError("Give at least one of type, area, sentiment or urgency")
        return self


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str = Field(min_length=1, max_length=300, examples=["terminal crashes when splitting"])
    type: TagType | None = None
    area: str | None = Field(default=None, max_length=64)
    state: Literal["open", "closed"] | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    include_maintainer: bool = False
    limit: int = Field(default=10, ge=1, le=50)


class SearchHitRead(BaseModel):
    item: FeedbackItemRead
    score: float
    # "words", "meaning", or both: which search found this item.
    matched_by: list[str]


class SearchResults(BaseModel):
    question: str
    searched_by_meaning: bool
    hits: list[SearchHitRead]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=300, examples=["What do users hate about chat?"])
    snippets: int = Field(default=8, ge=1, le=20)
    type: TagType | None = None
    area: str | None = Field(default=None, max_length=64)
    state: Literal["open", "closed"] | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    include_maintainer: bool = False


class CitedItemRead(BaseModel):
    number: int
    item: FeedbackItemRead


class AnswerRead(BaseModel):
    question_id: int | None
    question: str
    answer: str
    enough_evidence: bool
    considered_count: int
    sources: list[CitedItemRead]
    # Citation numbers the model made up, which were removed before you saw the answer.
    dropped_citations: list[int]


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    answer: str
    enough_evidence: bool
    helpful: bool | None
    created_at: datetime


class RatingUpdate(BaseModel):
    helpful: bool


class CsvImportResult(BaseModel):
    source: "SourceRead"
    created: int
    updated: int
    unchanged: int
    skipped: int
    # Rows that could not be used, and anything else worth telling the uploader.
    problems: list[str]


# ---------------------------------------------------------------------------
# Embeddable feedback widget — accepts user feedback from external sites.
# The widget is a small JS snippet that posts to POST /widget/submit.
# ---------------------------------------------------------------------------


class WidgetSubmission(BaseModel):
    """One piece of feedback sent by the embeddable widget.

    Only ``text`` is required.  The optional ``email`` and ``name`` let the
    submitter identify themselves, but they are scrubbed before storage so
    PII never reaches the database or an AI model.
    """

    text: str = Field(min_length=3, max_length=5000, examples=["The search is too slow"])
    # Optional — the submitter may choose to stay anonymous.
    email: str | None = Field(default=None, max_length=320)
    name: str | None = Field(default=None, max_length=120)


class WidgetSubmissionResult(BaseModel):
    """Returned after a widget submission is accepted."""

    item_id: int
    message: str = "Thank you for your feedback!"


class WidgetEmbed(BaseModel):
    """The embed snippet and configuration shown to workspace admins."""

    # The URL of the widget JS file to include in a script tag.
    script_url: str
    # The workspace slug the widget submits to.
    workspace_slug: str
    # The API base URL the widget will POST to.
    api_url: str
    # A ready-to-paste HTML snippet.
    snippet: str


class TicketDraftRequest(BaseModel):
    repo: str | None = Field(default=None, pattern=GITHUB_REPO_PATTERN)
    check_duplicates: bool = True


class DuplicateCandidateRead(BaseModel):
    number: int
    title: str
    url: str
    similarity: float


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    theme_id: int
    repo: str
    title: str
    body: str
    status: str
    duplicate_candidates: list[DuplicateCandidateRead]
    external_url: str | None
    external_id: str | None
    error: str | None
    filed_at: datetime | None
    created_at: datetime


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=120)
    body: str | None = Field(default=None, min_length=10, max_length=20_000)
    status: Literal["dismissed"] | None = None

    @model_validator(mode="after")
    def at_least_one_change(self) -> "TicketUpdate":
        if not self.model_dump(exclude_none=True):
            raise ValueError("Give a title, a body or a status")
        return self


class AlertRead(BaseModel):
    id: int
    theme_id: int
    theme_name: str
    week_start: date
    item_count: int
    baseline: float
    ratio: float
    status: str
    channel: str
    created_at: datetime


class ThemeWeekRead(BaseModel):
    week_start: date
    item_count: int


class ThemeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    summary: str
    status: str
    item_count: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    renamed_by_human: bool
    weeks: list[ThemeWeekRead] = []
    last_week_count: int = 0
    # The latest week compared with the weeks before it; 2.0 means twice as many as usual.
    growth: float | None = None


class ThemeDetail(ThemeRead):
    items: list[FeedbackItemRead] = []


class ThemeList(BaseModel):
    total: int
    themes: list[ThemeRead]


class ThemeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["open", "ignored"] | None = None

    @model_validator(mode="after")
    def at_least_one_change(self) -> "ThemeUpdate":
        if not self.model_dump(exclude_none=True):
            raise ValueError("Give a name or a status")
        return self


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    status: str
    attempts: int
    max_attempts: int
    run_after: datetime
    last_error: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AI cost tracking — aggregations over the ai_calls table.
# The raw data is already recorded by the tagging, embedding and answering
# modules (see app.ai.*); these schemas are purely for the read side.
# ---------------------------------------------------------------------------


class FeatureUsage(BaseModel):
    """Token and call totals for one AI feature (e.g. "tagging", "embedding", "ask")."""

    feature: str
    # How many times this feature called the model.
    total_calls: int
    # How many of those calls succeeded (the rest failed or errored).
    succeeded_calls: int
    # How many feedback items were processed across all calls.
    total_items: int
    # Raw token counts, straight from the model's usage metadata.
    input_tokens: int
    output_tokens: int
    # Average round-trip time to the model, in milliseconds.
    avg_latency_ms: float


class DailyUsage(BaseModel):
    """Token and call totals for one calendar day, across all features."""

    date: date
    total_calls: int
    succeeded_calls: int
    input_tokens: int
    output_tokens: int


class UsageSummary(BaseModel):
    """Everything the cost-tracking page needs in a single response.

    The estimated_cost_usd field is a rough number based on published Gemini
    pricing; it is meant to give a quick feel, not a billing-grade total.
    """

    # Lifetime totals for the whole workspace.
    total_calls: int
    succeeded_calls: int
    total_items: int
    input_tokens: int
    output_tokens: int
    # Sum of input + output, since dashboards almost always show this.
    total_tokens: int
    # A rough USD estimate: (input_tokens * input_price + output_tokens * output_price).
    estimated_cost_usd: float
    # Broken down by feature ("tagging", "embedding", "ask").
    by_feature: list[FeatureUsage]
    # Broken down by calendar day, most recent first, last 30 days.
    daily: list[DailyUsage]


# ---------------------------------------------------------------------------
# Evaluation report — mirrors the dataclasses in app.evals.scoring but as
# Pydantic models for the REST response.  The eval system scores AI tags
# against human-checked labels and reports accuracy per field.
# ---------------------------------------------------------------------------


class ClassScoreRead(BaseModel):
    """Precision, recall and F1 for a single label value (e.g. "bug" or "terminal")."""

    expected: int
    predicted: int
    correct: int
    precision: float
    recall: float
    f1: float


class FieldScoreRead(BaseModel):
    """Accuracy and per-class scores for one tagging field (e.g. "type" or "area")."""

    compared: int
    correct: int
    accuracy: float
    macro_f1: float
    # Per-class breakdown: label name → scores.
    per_class: dict[str, ClassScoreRead]
    # Most common mistakes: list of [expected, predicted, count].
    mistakes: list[list[str | int]]


class EvalReportRead(BaseModel):
    """The full evaluation report for one workspace.

    This is what the frontend displays on the /evals page.
    """

    workspace: str
    model: str | None
    prompt_version: str | None
    labelled_items: int
    checked_by_people: int
    scored_items: int
    skipped_corrected: int
    # One entry per tagging field: "type" and "area".
    fields: dict[str, FieldScoreRead]
