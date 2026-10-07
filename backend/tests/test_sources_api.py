import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Workspace


def create_source(client: TestClient, repo: str = "microsoft/vscode") -> int:
    response = client.post("/workspaces/test/sources/github", json={"repo": repo})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_create_and_list_github_source(client: TestClient, workspace: Workspace) -> None:
    response = client.post("/workspaces/test/sources/github", json={"repo": "microsoft/vscode"})

    assert response.status_code == 201
    body = response.json()
    assert (body["kind"], body["name"]) == ("github", "microsoft/vscode")
    assert body["config"] == {"repo": "microsoft/vscode", "backfill_days": 30, "max_items": 2000}
    assert [source["id"] for source in client.get("/workspaces/test/sources").json()] == [
        body["id"]
    ]


def test_duplicate_source_is_rejected(client: TestClient, workspace: Workspace) -> None:
    create_source(client)

    response = client.post("/workspaces/test/sources/github", json={"repo": "microsoft/vscode"})

    assert response.status_code == 409


@pytest.mark.parametrize("repo", ["vscode", "microsoft/", "micro soft/vscode", "../etc"])
def test_invalid_repo_is_rejected(client: TestClient, workspace: Workspace, repo: str) -> None:
    response = client.post("/workspaces/test/sources/github", json={"repo": repo})

    assert response.status_code == 422


def test_unknown_workspace_returns_404(client: TestClient, db: Session) -> None:
    assert client.get("/workspaces/nope/sources").status_code == 404


def test_sync_queues_a_single_job_per_source(client: TestClient, workspace: Workspace) -> None:
    source_id = create_source(client)

    first = client.post(f"/workspaces/test/sources/{source_id}/sync")
    second = client.post(f"/workspaces/test/sources/{source_id}/sync")

    assert first.status_code == 202
    assert first.json()["status"] == "queued"
    assert second.json()["id"] == first.json()["id"]
    job = client.get(f"/workspaces/test/jobs/{first.json()['id']}")
    assert job.status_code == 200
    assert job.json()["kind"] == "github_sync"


def test_cannot_touch_another_workspaces_source(
    client: TestClient, workspace: Workspace, other_workspace: Workspace
) -> None:
    source_id = create_source(client)

    assert client.post(f"/workspaces/other/sources/{source_id}/sync").status_code == 404
