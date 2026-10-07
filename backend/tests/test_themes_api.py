from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import EMBEDDING_DIMENSIONS
from app.models import FeedbackItem, Theme, ThemeItem, ThemeWeeklyStat, Workspace

MakeItem = Callable[..., FeedbackItem]
LAST_WEEK = date(2026, 9, 14)


def centroid(axis: int = 0) -> list[float]:
    values = [0.0] * EMBEDDING_DIMENSIONS
    values[axis] = 1.0
    return values


def make_theme(
    db: Session,
    workspace: Workspace,
    *,
    name: str,
    items: list[FeedbackItem],
    weekly: dict[date, int] | None = None,
    status: str = "open",
) -> Theme:
    theme = Theme(
        workspace_id=workspace.id,
        name=name,
        summary="",
        status=status,
        centroid=centroid(),
        item_count=len(items),
        name_model="medoid",
    )
    db.add(theme)
    db.flush()
    for position, item in enumerate(items):
        db.add(
            ThemeItem(
                item_id=item.id,
                theme_id=theme.id,
                workspace_id=workspace.id,
                similarity=1.0 - position / 10,
            )
        )
    for week_start, count in (weekly or {}).items():
        db.add(ThemeWeeklyStat(theme_id=theme.id, week_start=week_start, item_count=count))
    db.commit()
    return theme


def test_lists_themes_biggest_first_with_weekly_counts(
    client: TestClient, db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    big = make_theme(
        db,
        workspace,
        name="Terminal crashes",
        items=[make_item(number) for number in range(3)],
        weekly={LAST_WEEK - timedelta(weeks=1): 1, LAST_WEEK: 2},
    )
    make_theme(db, workspace, name="Chat is slow", items=[make_item(9)])

    body = client.get("/workspaces/test/themes").json()

    assert body["total"] == 2
    assert [theme["name"] for theme in body["themes"]] == ["Terminal crashes", "Chat is slow"]
    first = body["themes"][0]
    assert (first["id"], first["item_count"]) == (big.id, 3)
    assert first["last_week_count"] == 2
    assert len(first["weeks"]) == 8
    assert first["weeks"][-1] == {"week_start": LAST_WEEK.isoformat(), "item_count": 2}


def test_growth_compares_the_latest_week_with_the_weeks_before(
    client: TestClient, db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    weekly = {LAST_WEEK - timedelta(weeks=index): 1 for index in range(1, 5)}
    weekly[LAST_WEEK] = 4
    make_theme(db, workspace, name="Growing", items=[make_item(1)], weekly=weekly)

    theme = client.get("/workspaces/test/themes").json()["themes"][0]

    assert theme["growth"] == pytest.approx(4.0)


def test_hidden_themes_can_be_filtered(
    client: TestClient, db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    make_theme(db, workspace, name="Open one", items=[make_item(1)])
    make_theme(db, workspace, name="Hidden one", items=[make_item(2)], status="ignored")

    assert [t["name"] for t in client.get("/workspaces/test/themes").json()["themes"]] == [
        "Open one",
        "Hidden one",
    ]
    ignored = client.get("/workspaces/test/themes", params={"status": "ignored"}).json()
    assert [theme["name"] for theme in ignored["themes"]] == ["Hidden one"]


def test_theme_detail_lists_its_most_typical_items(
    client: TestClient, db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    items = [make_item(number) for number in range(3)]
    theme = make_theme(db, workspace, name="Terminal crashes", items=items)

    detail = client.get(f"/workspaces/test/themes/{theme.id}").json()

    assert detail["name"] == "Terminal crashes"
    assert [item["external_id"] for item in detail["items"]] == [item.external_id for item in items]


def test_renaming_a_theme_marks_it_as_human_named(
    client: TestClient, db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    theme = make_theme(db, workspace, name="Terminal crashes on split", items=[make_item(1)])

    response = client.patch(
        f"/workspaces/test/themes/{theme.id}", json={"name": "Terminal splits crash the window"}
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["renamed_by_human"]) == ("Terminal splits crash the window", True)
    db.expire_all()
    assert db.get(Theme, theme.id).name_model == "human"


def test_a_theme_can_be_hidden(
    client: TestClient, db: Session, workspace: Workspace, make_item: MakeItem
) -> None:
    theme = make_theme(db, workspace, name="Noise", items=[make_item(1)])

    response = client.patch(f"/workspaces/test/themes/{theme.id}", json={"status": "ignored"})

    assert response.json()["status"] == "ignored"


@pytest.mark.parametrize("changes", [{}, {"status": "nonsense"}, {"name": ""}])
def test_invalid_theme_changes_are_rejected(
    client: TestClient,
    db: Session,
    workspace: Workspace,
    make_item: MakeItem,
    changes: dict[str, Any],
) -> None:
    theme = make_theme(db, workspace, name="Theme", items=[make_item(1)])

    assert client.patch(f"/workspaces/test/themes/{theme.id}", json=changes).status_code == 422


def test_themes_are_workspace_scoped(
    client: TestClient,
    db: Session,
    workspace: Workspace,
    other_workspace: Workspace,
    make_item: MakeItem,
) -> None:
    theme = make_theme(db, workspace, name="Theme", items=[make_item(1)])

    assert client.get(f"/workspaces/other/themes/{theme.id}").status_code == 404


def test_recluster_queues_a_single_job(client: TestClient, workspace: Workspace) -> None:
    first = client.post("/workspaces/test/themes/recluster")
    second = client.post("/workspaces/test/themes/recluster")

    assert first.status_code == 202
    assert first.json()["kind"] == "cluster_items"
    assert second.json()["id"] == first.json()["id"]


def test_themes_with_no_items_are_hidden_from_the_list(
    client: TestClient, db: Session, workspace: Workspace
) -> None:
    db.add(
        Theme(
            workspace_id=workspace.id,
            name="Emptied out",
            centroid=centroid(),
            item_count=0,
            name_model="medoid",
        )
    )
    db.commit()

    assert client.get("/workspaces/test/themes").json()["total"] == 0
    assert db.scalars(select(Theme)).all() != []
