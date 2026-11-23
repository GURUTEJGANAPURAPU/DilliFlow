from fastapi.testclient import TestClient

from app import main


def test_commuter_health_is_public_and_operator_dashboard_is_protected(monkeypatch):
    monkeypatch.setattr(main, "startup_runtime_schema", lambda: None)
    monkeypatch.setattr(main, "require_db", lambda: None)
    monkeypatch.setattr(main.settings, "operator_id", "planner-01")
    monkeypatch.setattr(main.settings, "operator_password", "a-strong-test-password")
    monkeypatch.setattr(main.settings, "operator_token_secret", "test-signing-secret")
    monkeypatch.setattr(main, "operator_dashboard", lambda hour, day_type: {
        "selected_hour": hour,
        "day_type": day_type,
        "route_demand": [],
        "priority_segments": [],
    })

    with TestClient(main.app) as client:
        # Commuter-facing health is public and does not require a bearer token.
        assert client.get("/api/health").status_code == 200

        denied = client.get("/api/operator/dashboard?hour=8&day_type=weekday")
        assert denied.status_code == 401

        login = client.post("/api/operator/login", json={
            "operator_id": "planner-01",
            "password": "a-strong-test-password",
        })
        assert login.status_code == 200
        token = login.json()["access_token"]

        allowed = client.get(
            "/api/operator/dashboard?hour=8&day_type=weekday",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert allowed.status_code == 200
        assert allowed.json()["operator_id"] == "planner-01"

        wrong_password = client.post("/api/operator/login", json={
            "operator_id": "planner-01",
            "password": "incorrect-password",
        })
        assert wrong_password.status_code == 401
