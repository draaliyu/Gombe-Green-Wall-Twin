from app.config import _parse_bbox


def test_bbox_accepts_csv_and_json() -> None:
    assert _parse_bbox("10.55,10.20,11.85,11.55") == (10.55, 10.20, 11.85, 11.55)
    assert _parse_bbox("[10.55,10.20,11.85,11.55]") == (10.55, 10.20, 11.85, 11.55)


def test_bbox_rejects_invalid_order() -> None:
    try:
        _parse_bbox("11.85,10.20,10.55,11.55")
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid longitude order should fail")
