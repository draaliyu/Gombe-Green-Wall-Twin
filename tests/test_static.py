from pathlib import Path

from app.main import app


STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_service_pages_exist() -> None:
    for name in ["index.html", "satellite.html", "simulation.html", "planner.html", "evidence.html"]:
        assert (STATIC / name).exists()


def test_expected_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    expected = {
        "/api/snapshot",
        "/api/ndvi/grid",
        "/api/simulation/trees",
        "/api/planner/corridor",
        "/ws/live",
    }
    assert expected <= paths
