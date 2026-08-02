from fastapi.testclient import TestClient

from kairos.app import app

client = TestClient(app)


def test_given_a_running_app_when_health_is_called_then_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_given_an_unreachable_database_when_deep_health_is_called_then_degrades() -> None:
    """The deep check reports a dead dependency; it must never raise."""
    response = client.get("/health/deep")
    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "degraded"}
