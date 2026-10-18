"""Evaluation report endpoint.

Runs the eval scorer (app.evals.scoring.build_report) and returns the result
so the frontend can render an accuracy dashboard.  This is a read-only
endpoint — it scores what's already in the database, never modifies data.
"""

from fastapi import APIRouter

from app.api.deps import ReadableWorkspaceDep, SessionDep
from app.api.schemas import ClassScoreRead, EvalReportRead, FieldScoreRead
from app.evals.scoring import build_report

router = APIRouter(prefix="/workspaces/{slug}/evals", tags=["evals"])


@router.get("", response_model=EvalReportRead)
def get_eval_report(
    workspace: ReadableWorkspaceDep,
    session: SessionDep,
) -> EvalReportRead:
    """Score AI tags against checked labels and return the report.

    This calls build_report() from the evals module, which compares every
    AI-generated tag with its corresponding human-checked label, computes
    accuracy, precision, recall, F1, and lists the most common mistakes.

    The computation is done on the fly — there is no caching — because the
    checked set is small (a few hundred rows) and the query is fast.
    """
    # -- Run the scoring engine.  This is the same logic that the CLI
    #    (python -m app.evals score) uses, just exposed as an API.
    report = build_report(session, workspace)

    # -- Convert the dataclass report into the Pydantic response schema.
    #    We convert field by field so the types match exactly.
    fields: dict[str, FieldScoreRead] = {}
    for field_name, field_score in report.fields.items():
        per_class = {
            label: ClassScoreRead(
                expected=cs.expected,
                predicted=cs.predicted,
                correct=cs.correct,
                precision=round(cs.precision, 4),
                recall=round(cs.recall, 4),
                f1=round(cs.f1, 4),
            )
            for label, cs in field_score.per_class.items()
        }
        # Mistakes come as tuples (expected, predicted, count) from the scorer.
        # Convert to lists for JSON serialisation.
        mistakes = [
            [expected, predicted, count] for expected, predicted, count in field_score.mistakes
        ]
        fields[field_name] = FieldScoreRead(
            compared=field_score.compared,
            correct=field_score.correct,
            accuracy=round(field_score.accuracy, 4),
            macro_f1=round(field_score.macro_f1, 4),
            per_class=per_class,
            mistakes=mistakes,
        )

    return EvalReportRead(
        workspace=report.workspace,
        model=report.model,
        prompt_version=report.prompt_version,
        labelled_items=report.labelled_items,
        checked_by_people=report.checked_by_people,
        scored_items=report.scored_items,
        skipped_corrected=report.skipped_corrected,
        fields=fields,
    )
