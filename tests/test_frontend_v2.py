import re
from pathlib import Path

from app.main import app

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_v2_pages_and_scripts_exist() -> None:
    for name in ["index.html", "areas.html", "weather.html", "satellite.html", "simulation.html", "planner.html", "evidence.html"]:
        assert (STATIC / name).exists()
    for name in ["common.js", "sky.js", "trees3d.js", "twin.js", "areas.js", "weather.js", "planner.js"]:
        assert (STATIC / "js" / name).exists()


def test_pages_have_unique_ids() -> None:
    for page in STATIC.glob("*.html"):
        ids = re.findall(r'\bid=["\']([^"\']+)["\']', page.read_text(encoding="utf-8"))
        assert len(ids) == len(set(ids)), page.name


def test_v2_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    expected = {
        "/areas", "/weather", "/api/lgas", "/api/northern-lgas", "/api/areas",
        "/api/areas/{slug}", "/api/weather", "/api/weather/refresh",
    }
    assert expected <= paths


def test_planner_draft_is_not_browser_persistent() -> None:
    script = (STATIC / "js" / "planner.js").read_text(encoding="utf-8")
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert 'window.addEventListener("pageshow", () => clearDraft())' in script
    assert "clearDraft(\"Draft cleared after commit" in script


def test_full_state_and_northern_view_controls_exist() -> None:
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="view-state"' in page
    assert 'id="view-north"' in page
    common = (STATIC / "js" / "common.js").read_text(encoding="utf-8")
    assert "northern-focus-outline" in common
    assert "gombe-state-outline" in common


def test_social_preview_has_standard_dimensions() -> None:
    from PIL import Image

    with Image.open(STATIC / "social-preview.jpg") as image:
        assert image.size == (1200, 630)
