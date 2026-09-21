import pytest

from app.evals.label_map import expected_area, expected_type


@pytest.mark.parametrize(
    ("labels", "result"),
    [
        (["bug", "triage-needed"], "bug"),
        (["feature-request"], "feature_request"),
        (["*question"], "question"),
        # How an issue was handled says nothing about what kind of feedback it is.
        (["invalid"], None),
        (["triage-needed", "*duplicate"], None),
        ([], None),
        # Labels that disagree say nothing certain.
        (["bug", "feature-request"], None),
    ],
)
def test_expected_type(labels: list[str], result: str | None) -> None:
    assert expected_type(labels) == result


@pytest.mark.parametrize(
    ("labels", "result"),
    [
        (["terminal"], "terminal"),
        (["notebook-cell-execution"], "notebooks"),
        (["git"], "source-control"),
        (["chat-agents"], "chat-ai"),
        (["editor-find"], "editor"),
        (["perf"], "performance"),
        (["bug", "triage-needed"], None),
        ([], None),
    ],
)
def test_expected_area(labels: list[str], result: str | None) -> None:
    assert expected_area(labels) == result
