from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_database_and_pgvector() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "ok"
    assert body["pgvector"] is not None, "run `alembic upgrade head` to enable pgvector"
