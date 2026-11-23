from app.ingest import is_missing, norm, to_float


def test_normalizes_route_and_stop_labels():
    assert norm("  19-UP / Central   ") == "19 up central"


def test_detects_missing_vehicle_values():
    for value in (None, "", " NULL ", "NaN", "N/A", "-"):
        assert is_missing(value)
    assert not is_missing("DL1PD7049")


def test_safe_numeric_conversion():
    assert to_float("2.5") == 2.5
    assert to_float("NULL") == 0.0
