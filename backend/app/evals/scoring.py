"""Compare AI tags against the checked labels and report how good they are."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import fmean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvalLabel, ItemTag, Workspace

TOP_MISTAKES = 5


@dataclass(frozen=True)
class ClassScore:
    expected: int
    predicted: int
    correct: int
    precision: float
    recall: float
    f1: float


@dataclass(frozen=True)
class FieldScore:
    compared: int
    correct: int
    accuracy: float
    macro_f1: float
    per_class: dict[str, ClassScore]
    mistakes: list[tuple[str, str, int]]


@dataclass
class EvalReport:
    workspace: str
    model: str | None
    prompt_version: str | None
    labelled_items: int
    checked_by_people: int
    scored_items: int
    skipped_corrected: int
    fields: dict[str, FieldScore] = field(default_factory=dict)


def score_field(pairs: Sequence[tuple[str, str]]) -> FieldScore:
    """Accuracy, per-label precision/recall/F1 and macro F1 for (expected, predicted) pairs."""
    names = sorted({expected for expected, _ in pairs} | {predicted for _, predicted in pairs})
    per_class: dict[str, ClassScore] = {}
    for name in names:
        expected_count = sum(1 for expected, _ in pairs if expected == name)
        predicted_count = sum(1 for _, predicted in pairs if predicted == name)
        correct = sum(1 for expected, predicted in pairs if expected == name == predicted)
        precision = correct / predicted_count if predicted_count else 0.0
        recall = correct / expected_count if expected_count else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[name] = ClassScore(
            expected_count, predicted_count, correct, precision, recall, f1
        )

    correct_total = sum(1 for expected, predicted in pairs if expected == predicted)
    mistakes = Counter(
        (expected, predicted) for expected, predicted in pairs if expected != predicted
    )
    return FieldScore(
        compared=len(pairs),
        correct=correct_total,
        accuracy=correct_total / len(pairs) if pairs else 0.0,
        macro_f1=fmean(score.f1 for score in per_class.values()) if per_class else 0.0,
        per_class=per_class,
        mistakes=[
            (expected, predicted, count)
            for (expected, predicted), count in mistakes.most_common(TOP_MISTAKES)
        ],
    )


def build_report(session: Session, workspace: Workspace) -> EvalReport:
    rows = session.execute(
        select(EvalLabel, ItemTag)
        .join(ItemTag, ItemTag.item_id == EvalLabel.item_id, isouter=True)
        .where(EvalLabel.workspace_id == workspace.id)
    ).all()

    # Tags a person corrected match the checked answer by definition, so scoring them
    # would only flatter the model.
    scored = [(label, tag) for label, tag in rows if tag is not None and not tag.reviewed_by_human]
    type_pairs = [
        (label.expected_type, tag.type) for label, tag in scored if label.expected_type is not None
    ]
    area_pairs = [
        (label.expected_area, tag.area) for label, tag in scored if label.expected_area is not None
    ]

    return EvalReport(
        workspace=workspace.slug,
        model=_single_value(tag.model for _, tag in scored),
        prompt_version=_single_value(tag.prompt_version for _, tag in scored),
        labelled_items=len(rows),
        checked_by_people=sum(1 for label, _ in rows if label.source == "human"),
        scored_items=len(scored),
        skipped_corrected=sum(1 for _, tag in rows if tag is not None and tag.reviewed_by_human),
        fields={"type": score_field(type_pairs), "area": score_field(area_pairs)},
    )


def _single_value(values: object) -> str | None:
    unique = sorted(set(values))  # type: ignore[call-overload]
    if not unique:
        return None
    return unique[0] if len(unique) == 1 else ", ".join(unique)
