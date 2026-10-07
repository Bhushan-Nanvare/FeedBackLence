from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvalLabel, FeedbackItem, ItemTag, ProductArea, Workspace

MakeItem = Callable[..., FeedbackItem]


@pytest.fixture
def areas(db: Session, workspace: Workspace) -> None:
    db.add(ProductArea(workspace_id=workspace.id, slug="editor", name="Editor"))
    db.commit()


def tag_item(db: Session, item: FeedbackItem, **overrides: Any) -> ItemTag:
    values: dict[str, Any] = {
        "type": "bug",
        "area": "editor",
        "sentiment": "negative",
        "urgency": "medium",
        "confidence": 0.9,
        "summary": "The editor freezes.",
        "content_hash": item.content_hash,
        "model": "fake-model",
        "prompt_version": "tag-v1",
    }
    values.update(overrides)
    tag = ItemTag(item_id=item.id, workspace_id=item.workspace_id, **values)
    db.add(tag)
    db.commit()
    return tag


def listed(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/workspaces/test/items", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_lists_newest_first_and_hides_maintainer_items(
    client: TestClient, make_item: MakeItem
) -> None:
    make_item(1)
    newest = make_item(2)
    make_item(3, maintainer=True)

    page = listed(client)

    assert page["total"] == 2
    assert [item["external_id"] for item in page["items"]] == [newest.external_id, "1"]
    assert page["items"][0]["tag"] is None

    with_maintainers = listed(client, include_maintainer=True)
    assert with_maintainers["total"] == 3


def test_paging_and_sorting(client: TestClient, db: Session, make_item: MakeItem) -> None:
    for number in (1, 2, 3):
        item = make_item(number)
        item.reactions_count = number
    db.commit()

    first_page = listed(client, limit=2)
    second_page = listed(client, limit=2, offset=2)

    assert (first_page["total"], len(first_page["items"])) == (3, 2)
    assert [item["external_id"] for item in second_page["items"]] == ["1"]
    assert [item["external_id"] for item in listed(client, sort="oldest")["items"]] == [
        "1",
        "2",
        "3",
    ]
    assert listed(client, sort="most_reactions")["items"][0]["external_id"] == "3"


def test_filters_by_tag_fields_state_and_untagged(
    client: TestClient, db: Session, make_item: MakeItem
) -> None:
    bug = make_item(1)
    request = make_item(2)
    untagged = make_item(3)
    tag_item(db, bug)
    tag_item(db, request, type="feature_request", area="terminal", urgency="low")
    closed = make_item(4)
    closed.state = "closed"
    db.commit()
    tag_item(db, closed)

    assert [i["external_id"] for i in listed(client, type="bug")["items"]] == ["4", "1"]
    assert [i["external_id"] for i in listed(client, area="terminal")["items"]] == ["2"]
    assert [i["external_id"] for i in listed(client, urgency="low")["items"]] == ["2"]
    assert [i["external_id"] for i in listed(client, sentiment="negative")["items"]] == [
        "4",
        "2",
        "1",
    ]
    assert [i["external_id"] for i in listed(client, state="closed")["items"]] == ["4"]
    assert [i["external_id"] for i in listed(client, untagged=True)["items"]] == [
        untagged.external_id
    ]
    assert listed(client, type="bug")["items"][0]["tag"]["summary"] == "The editor freezes."


def test_search_matches_title_or_body_and_escapes_wildcards(
    client: TestClient, make_item: MakeItem
) -> None:
    make_item(1, body="Battery drains at 100% CPU usage.")
    make_item(2, body="Something else entirely.")

    assert [i["external_id"] for i in listed(client, q="battery")["items"]] == ["1"]
    assert [i["external_id"] for i in listed(client, q="Issue 2")["items"]] == ["2"]
    # "%" must be treated as text, not as a wildcard that matches everything.
    assert [i["external_id"] for i in listed(client, q="100%")["items"]] == ["1"]
    assert listed(client, q="nothing here")["total"] == 0


@pytest.mark.parametrize(
    "params",
    [{"type": "nonsense"}, {"limit": 999}, {"offset": -1}, {"sort": "random"}, {"unknown": "x"}],
)
def test_invalid_filters_are_rejected(
    client: TestClient, workspace: Workspace, params: dict[str, Any]
) -> None:
    assert client.get("/workspaces/test/items", params=params).status_code == 422


def test_item_detail_includes_body_and_is_workspace_scoped(
    client: TestClient, make_item: MakeItem, workspace: Workspace, other_workspace: Workspace
) -> None:
    item = make_item(1)

    detail = client.get(f"/workspaces/test/items/{item.id}")

    assert detail.status_code == 200
    assert detail.json()["body_clean"] == item.body_clean
    assert client.get(f"/workspaces/other/items/{item.id}").status_code == 404


def test_correcting_a_tag_marks_it_reviewed(
    client: TestClient, db: Session, make_item: MakeItem, areas: None
) -> None:
    item = make_item(1)
    tag_item(db, item)

    response = client.patch(f"/workspaces/test/items/{item.id}/tag", json={"type": "question"})

    assert response.status_code == 200
    body = response.json()
    assert (body["type"], body["reviewed_by_human"]) == ("question", True)
    # Untouched fields keep their values.
    assert (body["area"], body["urgency"]) == ("editor", "medium")


def test_correcting_an_untagged_item_creates_the_tag(
    client: TestClient, make_item: MakeItem, areas: None
) -> None:
    item = make_item(1)

    response = client.patch(
        f"/workspaces/test/items/{item.id}/tag", json={"type": "praise", "area": "editor"}
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["type"], body["area"], body["reviewed_by_human"]) == ("praise", "editor", True)
    assert listed(client)["items"][0]["tag"]["type"] == "praise"


def test_correction_becomes_a_checked_label(
    client: TestClient, db: Session, make_item: MakeItem, areas: None
) -> None:
    item = make_item(1)

    client.patch(f"/workspaces/test/items/{item.id}/tag", json={"type": "bug", "area": "editor"})

    label = db.scalars(select(EvalLabel)).one()
    assert (label.item_id, label.expected_type, label.expected_area, label.source) == (
        item.id,
        "bug",
        "editor",
        "human",
    )


@pytest.mark.parametrize(
    "changes",
    [{"area": "made-up-area"}, {"type": "nonsense"}, {}],
)
def test_invalid_corrections_are_rejected(
    client: TestClient, make_item: MakeItem, areas: None, changes: dict[str, Any]
) -> None:
    item = make_item(1)

    assert client.patch(f"/workspaces/test/items/{item.id}/tag", json=changes).status_code == 422
