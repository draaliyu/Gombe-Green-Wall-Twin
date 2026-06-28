from app.services.boundary import GOMBE_LGA_NAMES, NORTHERN_LGA_NAMES, fallback_lgas, location_points, northern_lgas


def test_fallback_contains_all_gombe_lgas() -> None:
    collection = fallback_lgas()
    names = {feature["properties"]["name"] for feature in collection["features"]}
    assert names == set(GOMBE_LGA_NAMES)
    assert len(collection["features"]) == 11


def test_northern_focus_contains_five_lgas() -> None:
    collection = northern_lgas(fallback_lgas())
    names = {feature["properties"]["name"] for feature in collection["features"]}
    assert names == set(NORTHERN_LGA_NAMES)
    assert len(collection["features"]) == 5


def test_location_points_match_lgas() -> None:
    points = location_points(fallback_lgas())
    assert len(points["features"]) == 11
    assert all(feature["geometry"]["type"] == "Point" for feature in points["features"])
