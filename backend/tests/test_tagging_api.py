from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import FeedbackItem, ItemTag, Workspace


def test_replace_and_list_product_areas(client: TestClient, workspace: Workspace) -> None:
    response = client.put(
        "/workspaces/test/product-areas",
        json=[
            {"slug": "terminal", "name": "Terminal", "description": "Integrated terminal"},
            {"slug": "editor", "name": "Editor"},
        ],
    )

    assert response.status_code == 200
    assert [area["slug"] for area in response.json()] == ["editor", "terminal"]

    client.put("/workspaces/test/product-areas", json=[{"slug": "git", "name": "Git"}])
    listed = client.get("/workspaces/test/product-areas").json()
    assert [area["slug"] for area in listed] == ["git"]


@pytest.mark.parametrize(
    "areas",
    [
        [{"slug": "other", "name": "Other"}],
        [{"slug": "Bad Slug", "name": "Bad"}],
        [{"slug": "git", "name": "Git"}, {"slug": "git", "name": "Git again"}],
    ],
)
def test_invalid_product_areas_are_rejected(
    client: TestClient, workspace: Workspace, areas: list[dict[str, Any]]
) -> None:
    assert client.put("/workspaces/test/product-areas", json=areas).status_code == 422


def test_tagging_run_queues_a_single_job(client: TestClient, workspace: Workspace) -> None:
    first = client.post("/workspaces/test/tagging/run")
    second = client.post("/workspaces/test/tagging/run")

    assert first.status_code == 202
    assert first.json()["kind"] == "tag_items"
    assert second.json()["id"] == first.json()["id"]


def test_tagging_status_counts_items(
    client: TestClient, db: Session, make_item: Callable[..., FeedbackItem]
) -> None:
    tagged = make_item(1)
    make_item(2)
    make_item(3, maintainer=True)
    db.add(
        ItemTag(
            item_id=tagged.id,
            workspace_id=tagged.workspace_id,
            type="bug",
            area="editor",
            sentiment="negative",
            urgency="high",
            confidence=0.8,
            summary="The editor freezes.",
            content_hash=tagged.content_hash,
            model="fake-model",
            prompt_version="tag-v1",
        )
    )
    db.commit()

    status = client.get("/workspaces/test/tagging/status").json()

    assert status == {
        "total_items": 3,
        "maintainer_items": 1,
        "tagged_items": 1,
        "reviewed_by_human": 0,
        "pending_items": 1,
        "by_type": {"bug": 1},
    }
