"""Evaluation CLI: `python -m app.evals build` then `python -m app.evals score`."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.evals.dataset import DEFAULT_DRAFT_LIMIT, build_draft_labels
from app.evals.scoring import EvalReport, build_report
from app.models import Workspace

DEFAULT_MAX_DROP = 3.0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.evals", description="Measure tagging accuracy against checked labels."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    # Shared options, so they work after the command name too.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", default="demo", help="workspace slug (default: demo)")

    build = commands.add_parser(
        "build", parents=[common], help="draft checked labels from the source's own labels"
    )
    build.add_argument("--limit", type=int, default=DEFAULT_DRAFT_LIMIT)

    score = commands.add_parser(
        "score", parents=[common], help="compare AI tags with the checked labels"
    )
    score.add_argument("--json", type=Path, help="also write the report as JSON")
    score.add_argument("--baseline", type=Path, help="compare against this saved report")
    score.add_argument("--save-baseline", type=Path, help="write this report as the new baseline")
    score.add_argument(
        "--max-drop",
        type=float,
        default=DEFAULT_MAX_DROP,
        help=f"fail if a score drops more than this many points (default: {DEFAULT_MAX_DROP})",
    )

    args = parser.parse_args()

    with SessionLocal() as session:
        workspace = session.scalar(select(Workspace).where(Workspace.slug == args.workspace))
        if workspace is None:
            print(f"No workspace named '{args.workspace}'.", file=sys.stderr)
            return 2

        if args.command == "build":
            stats = build_draft_labels(session, workspace.id, limit=args.limit)
            print(
                f"Draft labels: {stats.created} created, {stats.updated} updated, "
                f"{stats.no_usable_labels} items had no usable labels."
            )
            print("Review them in the inbox; your corrections replace the drafts.")
            return 0

        report = build_report(session, workspace)

    print(format_report(report))
    for path in (args.json, args.save_baseline):
        if path is not None:
            write_json(path, report)

    if args.baseline is not None and args.baseline.exists():
        regressions = compare_with_baseline(
            report, json.loads(args.baseline.read_text(encoding="utf-8")), args.max_drop
        )
        for line in regressions:
            print(line, file=sys.stderr)
        if regressions:
            return 1
    return 0


def format_report(report: EvalReport) -> str:
    lines = [
        f"Tagging accuracy — workspace {report.workspace}",
        f"Model: {report.model or 'nothing tagged yet'} (prompt {report.prompt_version or 'n/a'})",
        "",
        f"Checked labels: {report.labelled_items} "
        f"({report.checked_by_people} checked by a person, the rest drafted from source labels)",
        f"Scored: {report.scored_items} AI-tagged items "
        f"({report.skipped_corrected} corrected by a person and left out)",
        "",
    ]
    for name, score in report.fields.items():
        if score.compared == 0:
            lines += [f"{name}: nothing to compare yet", ""]
            continue
        lines.append(
            f"{name}: {score.accuracy:.1%} correct ({score.correct}/{score.compared}), "
            f"macro F1 {score.macro_f1:.2f}"
        )
        for label, per_class in sorted(score.per_class.items()):
            lines.append(
                f"    {label:<16} expected {per_class.expected:>4}  "
                f"predicted {per_class.predicted:>4}  correct {per_class.correct:>4}  "
                f"P {per_class.precision:.2f}  R {per_class.recall:.2f}  F1 {per_class.f1:.2f}"
            )
        if score.mistakes:
            worst = ", ".join(f"{a} → {b} ×{count}" for a, b, count in score.mistakes)
            lines.append(f"    most common mistakes: {worst}")
        lines.append("")
    return "\n".join(lines).rstrip()


def compare_with_baseline(report: EvalReport, baseline: dict, max_drop: float) -> list[str]:
    """Return a message for every score that fell further than `max_drop` points."""
    regressions = []
    for name, score in report.fields.items():
        previous = baseline.get("fields", {}).get(name)
        if not previous:
            continue
        for metric in ("accuracy", "macro_f1"):
            drop = (previous[metric] - getattr(score, metric)) * 100
            if drop > max_drop:
                regressions.append(
                    f"{name} {metric} fell {drop:.1f} points "
                    f"({previous[metric]:.3f} → {getattr(score, metric):.3f})"
                )
    return regressions


def write_json(path: Path, report: EvalReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
