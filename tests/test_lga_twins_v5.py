from __future__ import annotations

import re
from pathlib import Path

from app.main import app
from app.services.boundary import GOMBE_LGA_NAMES

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_all_eleven_gombe_lgas_are_declared() -> None:
    assert len(GOMBE_LGA_NAMES) == 11
    assert set(GOMBE_LGA_NAMES) == {
        "Akko", "Balanga", "Billiri", "Dukku", "Funakaye", "Gombe",
        "Kaltungo", "Kwami", "Nafada", "Shongom", "Yamaltu/Deba",
    }


def test_v5_lga_twin_routes_registered() -> None:
    paths = {route.path for route in app.routes}
    assert {
        "/lga/{slug}",
        "/api/lga-twins",
        "/api/lga-twins/{slug}/snapshot",
        "/api/lga-twins/{slug}/boundary",
        "/api/lga-twins/{slug}/textures/{layer}.png",
        "/api/lga-twins/{slug}/scenario",
        "/api/lga-twins/{slug}/projects",
        "/api/lga-twins/{slug}/field-observations",
        "/api/admin/lga-twins/{slug}/refresh-satellite",
        "/ws/lga/{slug}",
    } <= paths


def test_lga_twin_frontend_contains_live_microservice_controls() -> None:
    html = (STATIC / "lga-twin.html").read_text(encoding="utf-8")
    required_ids = {
        "lga-select", "lga-map", "lga-orbit", "lga-ground", "lga-full",
        "lga-timeline-chart", "lga-forecast-chart", "local-run-scenario",
        "lga-interpretations", "lga-provenance", "lga-limitations",
    }
    ids = set(re.findall(r'id="([^"]+)"', html))
    assert required_ids <= ids
    assert len(ids) == len(re.findall(r'id="([^"]+)"', html))


def test_lga_frontend_has_five_environmental_layers() -> None:
    html = (STATIC / "lga-twin.html").read_text(encoding="utf-8")
    for layer in ("ndvi", "simulation", "landcover", "suitability", "risk"):
        assert f'data-layer="{layer}"' in html


def test_lga_javascript_uses_dedicated_live_socket_and_api() -> None:
    script = (STATIC / "js" / "lga-twin.js").read_text(encoding="utf-8")
    assert "/ws/lga/" in script
    assert "/api/lga-twins/" in script
    assert "requestAnimationFrame(orbitLoop)" in script
    assert "localStorage" not in script
