from app.security import create_operator_token, verify_operator_credentials, verify_operator_token


def test_operator_credentials_use_constant_configured_values():
    assert verify_operator_credentials("planner-01", "secret-pass", "planner-01", "secret-pass")
    assert not verify_operator_credentials("planner-01", "wrong", "planner-01", "secret-pass")
    assert not verify_operator_credentials("other", "secret-pass", "planner-01", "secret-pass")
    assert not verify_operator_credentials("planner-01", "secret-pass", "", "")


def test_operator_token_is_signed_and_expires():
    token = create_operator_token("planner-01", "test-signing-secret", ttl_seconds=3600, now=1000)
    payload = verify_operator_token(token, "test-signing-secret", now=1200)
    assert payload and payload["sub"] == "planner-01"
    assert verify_operator_token(token, "wrong-signing-secret", now=1200) is None
    assert verify_operator_token(token, "test-signing-secret", now=5000) is None


def test_capacity_classification_only_uses_configured_capacity():
    from app.services.transit import _crowd_classification

    assert _crowd_classification("high", 25, {"seat_capacity": 35, "standing_capacity": 20, "capacity_configured": True})[0] == "seats_available"
    assert _crowd_classification("low", 45, {"seat_capacity": 35, "standing_capacity": 20, "capacity_configured": True})[0] == "standing_room"
    assert _crowd_classification("moderate", 60, {"seat_capacity": 35, "standing_capacity": 20, "capacity_configured": True})[0] == "crowded"
    assert _crowd_classification("high", None, {"seat_capacity": 35, "standing_capacity": 20, "capacity_configured": True})[0] == "high"
    assert _crowd_classification("moderate", 30, None)[0] == "moderate"
    assert _crowd_classification("high", 25, {"seat_capacity": 35, "standing_capacity": 20, "capacity_configured": False})[0] == "high"
