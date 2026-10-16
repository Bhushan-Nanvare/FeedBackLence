"""AI cost tracking endpoint.

Every AI call (tagging, embedding, answering) is already recorded in the
``ai_calls`` table by the modules in ``app.ai``.  This route aggregates those
rows so the frontend can show how much AI usage a workspace is consuming.

No new data is written here — this is a read-only aggregation endpoint.
"""

from datetime import timedelta

from fastapi import APIRouter, Query
from sqlalchemy import case, cast, func, select
from sqlalchemy.types import Date

from app.api.deps import ReadableWorkspaceDep, SessionDep
from app.api.schemas import DailyUsage, FeatureUsage, UsageSummary
from app.models import AiCall

router = APIRouter(prefix="/workspaces/{slug}/ai", tags=["ai-usage"])

# ---------------------------------------------------------------------------
# Rough per-token prices for Gemini models (USD).
#
# These are ballpark numbers taken from Google's published pricing page.
# They are only used for the "estimated cost" indicator on the dashboard;
# real billing comes from the Google Cloud console.  The prices are per
# 1 million tokens.
# ---------------------------------------------------------------------------
_INPUT_PRICE_PER_M = 0.075  # $0.075 per 1M input tokens  (Gemini Flash-Lite)
_OUTPUT_PRICE_PER_M = 0.30  # $0.30  per 1M output tokens (Gemini Flash-Lite)

# How many calendar days of per-day breakdown to return.
_DAILY_WINDOW_DAYS = 30


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Turn raw token counts into a rough USD figure.

    The formula is:
        cost = (input_tokens / 1_000_000) * input_price
             + (output_tokens / 1_000_000) * output_price

    This is intentionally simple — it uses a single model's pricing and
    does not try to look up per-model rates.  The number is an indicator,
    not an invoice.
    """
    return round(
        (input_tokens / 1_000_000) * _INPUT_PRICE_PER_M
        + (output_tokens / 1_000_000) * _OUTPUT_PRICE_PER_M,
        6,  # keep enough decimal places for small numbers
    )


@router.get("/usage", response_model=UsageSummary)
def get_usage(
    workspace: ReadableWorkspaceDep,
    session: SessionDep,
    days: int = Query(
        default=_DAILY_WINDOW_DAYS,
        ge=1,
        le=365,
        description="How many days of daily breakdown to return.",
    ),
) -> UsageSummary:
    """Aggregate AI usage for a workspace.

    Returns lifetime totals, a per-feature breakdown, and a per-day breakdown
    for the last ``days`` calendar days (default 30).
    """

    # ------------------------------------------------------------------
    # 1. Lifetime totals — one row, summing every ai_call in this workspace.
    # ------------------------------------------------------------------
    totals_query = select(
        func.count().label("total_calls"),
        # count only rows where succeeded is True
        func.count().filter(AiCall.succeeded.is_(True)).label("succeeded_calls"),
        func.coalesce(func.sum(AiCall.items_count), 0).label("total_items"),
        func.coalesce(func.sum(AiCall.input_tokens), 0).label("input_tokens"),
        func.coalesce(func.sum(AiCall.output_tokens), 0).label("output_tokens"),
    ).where(AiCall.workspace_id == workspace.id)

    row = session.execute(totals_query).one()

    total_calls: int = row.total_calls
    succeeded_calls: int = row.succeeded_calls
    total_items: int = row.total_items
    input_tokens: int = row.input_tokens
    output_tokens: int = row.output_tokens

    # ------------------------------------------------------------------
    # 2. Per-feature breakdown — one row per distinct feature value.
    #
    #    The feature column holds strings like "tagging", "embedding",
    #    "ask".  We group by it and sum up the same columns.
    # ------------------------------------------------------------------
    feature_query = (
        select(
            AiCall.feature,
            func.count().label("total_calls"),
            func.count().filter(AiCall.succeeded.is_(True)).label("succeeded_calls"),
            func.coalesce(func.sum(AiCall.items_count), 0).label("total_items"),
            func.coalesce(func.sum(AiCall.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AiCall.output_tokens), 0).label("output_tokens"),
            # Average latency: only count calls that actually ran (latency > 0).
            func.coalesce(
                func.avg(
                    case(
                        (AiCall.latency_ms > 0, AiCall.latency_ms),
                        else_=None,
                    )
                ),
                0,
            ).label("avg_latency_ms"),
        )
        .where(AiCall.workspace_id == workspace.id)
        .group_by(AiCall.feature)
        .order_by(AiCall.feature)
    )

    by_feature = [
        FeatureUsage(
            feature=f.feature,
            total_calls=f.total_calls,
            succeeded_calls=f.succeeded_calls,
            total_items=f.total_items,
            input_tokens=f.input_tokens,
            output_tokens=f.output_tokens,
            avg_latency_ms=round(f.avg_latency_ms, 1),
        )
        for f in session.execute(feature_query).all()
    ]

    # ------------------------------------------------------------------
    # 3. Per-day breakdown — one row per calendar day, last N days.
    #
    #    We cast the timestamp to a date and group by it.  Days with no
    #    calls simply do not appear (the frontend can fill the gaps).
    # ------------------------------------------------------------------
    cutoff = func.now() - timedelta(days=days)
    day_col = cast(AiCall.created_at, Date).label("day")

    daily_query = (
        select(
            day_col,
            func.count().label("total_calls"),
            func.count().filter(AiCall.succeeded.is_(True)).label("succeeded_calls"),
            func.coalesce(func.sum(AiCall.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AiCall.output_tokens), 0).label("output_tokens"),
        )
        .where(AiCall.workspace_id == workspace.id, AiCall.created_at >= cutoff)
        .group_by(day_col)
        .order_by(day_col.desc())
    )

    daily = [
        DailyUsage(
            date=d.day,
            total_calls=d.total_calls,
            succeeded_calls=d.succeeded_calls,
            input_tokens=d.input_tokens,
            output_tokens=d.output_tokens,
        )
        for d in session.execute(daily_query).all()
    ]

    # ------------------------------------------------------------------
    # 4. Assemble and return.
    # ------------------------------------------------------------------
    return UsageSummary(
        total_calls=total_calls,
        succeeded_calls=succeeded_calls,
        total_items=total_items,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated_cost_usd=_estimate_cost(input_tokens, output_tokens),
        by_feature=by_feature,
        daily=daily,
    )
