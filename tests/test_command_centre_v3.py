from pathlib import Path

from app.main import app
from app.services.weather import _demo_forecast

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_command_centre_controls_and_visuals_exist() -> None:
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    for marker in [
        'id="view-globe"',
        'id="toggle-terrain"',
        'id="toggle-orbit"',
        'id="first-person"',
        'id="split-view"',
        'id="weather-flow-canvas"',
        'id="sky-dome"',
        'id="forecast-chart"',
        'id="event-list"',
    ]:
        assert marker in page


def test_command_centre_scripts_exist() -> None:
    for name in ["dashboard.js", "twin.js", "sky.js", "trees3d.js"]:
        assert (STATIC / "js" / name).exists()


def test_weather_forecast_is_labelled_and_complete() -> None:
    forecast = _demo_forecast(11.2, 10.8, "Northern Gombe", "test")
    assert forecast.mode == "demo"
    assert len(forecast.points) == 24
    assert forecast.points[0].timestamp < forecast.points[-1].timestamp
    assert "not a provider forecast" in forecast.note.lower()


def test_weather_forecast_and_tile_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/weather/forecast" in paths
    assert "/api/weather/tiles/{layer}/{z}/{x}/{y}.png" in paths


def test_asset_cache_version_is_v5() -> None:
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "styles.css?v=5.0.0" in page
    assert "twin.js?v=5.0.0" in page
