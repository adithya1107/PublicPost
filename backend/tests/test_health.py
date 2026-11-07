from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import create_app


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


def test_health_reports_database_failure() -> None:
    class BrokenSession:
        def execute(self, _statement):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    app = create_app()
    app.dependency_overrides[get_db] = BrokenSession
    response = TestClient(app).get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
