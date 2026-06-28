from __future__ import annotations

from pathlib import Path

import numpy as np

from app.config import Settings
from app.main import app
from app.services.intelligence import IntelligenceEngine
from app.services.prediction import PredictionService

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_v4_pages_exist() -> None:
    names = [
        "services.html", "timeline.html", "drought.html", "landcover.html", "radar.html",
        "restoration.html", "ecosystems.html", "risks.html", "scenarios.html", "field.html",
        "projects.html", "predictions.html", "compare.html",
    ]
    for name in names:
        assert (STATIC / name).exists(), name


def test_v4_routes_registered() -> None:
    paths = {route.path for route in app.routes}
    expected = {
        "/api/intelligence/summary", "/api/temporal", "/api/rainfall", "/api/radar",
        "/api/landcover", "/api/suitability", "/api/suitability/routes", "/api/carbon",
        "/api/risks", "/api/fires", "/api/scenarios", "/api/predictions/forecast",
        "/api/admin/predictions/retrain", "/api/admin/temporal/backfill",
        "/api/field/observations", "/api/projects",
    }
    assert expected <= paths


def test_route_optimiser_returns_three_options(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, cache_dir=tmp_path / "cache", database_path=tmp_path / "db.sqlite3", model_path=tmp_path / "model.json")
    engine = IntelligenceEngine(settings)
    grid = np.linspace(0.1, 0.95, 36 * 48, dtype=np.float32).reshape(36, 48)
    result = engine.optimise_routes(grid, settings.aoi_bbox)
    assert len(result["routes"]) == 3
    assert all(route["coordinates"] for route in result["routes"])
    assert all(route["length_km"] > 0 for route in result["routes"])


def test_prediction_service_trains_and_forecasts(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        database_path=tmp_path / "db.sqlite3",
        model_path=tmp_path / "model.json",
        prediction_min_samples=8,
    )
    service = PredictionService(settings)
    points = []
    for index in range(24):
        year = 2024 + index // 12
        month = index % 12 + 1
        ndvi = 0.28 + 0.08 * np.sin(month / 12 * np.pi * 2) + index * 0.001
        points.append({
            "period": f"{year:04d}-{month:02d}", "ndvi": float(ndvi),
            "rain_mm": float(60 + 50 * np.sin((month - 4) / 12 * np.pi * 2)),
            "desert_fraction": float(max(0, 0.6 - ndvi)),
            "vegetated_fraction": float(min(1, ndvi + 0.3)),
        })
    model = service.train(points, "test")
    assert model["samples"] >= 8
    forecast = service.forecast(points, 6)
    assert forecast["available"] is True
    assert len(forecast["predictions"]) == 6


def test_new_pages_have_unique_ids() -> None:
    import re
    for path in STATIC.glob("*.html"):
        text = path.read_text(encoding="utf-8")
        ids = re.findall(r'id="([^"]+)"', text)
        assert len(ids) == len(set(ids)), path.name


def test_planner_does_not_persist_draft_in_browser_storage() -> None:
    text = (STATIC / "js" / "planner.js").read_text(encoding="utf-8")
    assert "localStorage" not in text
    assert "sessionStorage" not in text
