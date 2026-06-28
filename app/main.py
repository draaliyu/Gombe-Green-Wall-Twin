from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field

from app.config import get_settings
from app.models import ScenarioParameters
from app.services.enhanced_runtime import EnhancedTwinRuntime
from app.services.texture import make_social_preview

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger("green-wall-twin")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
settings = get_settings()
runtime = EnhancedTwinRuntime(settings)


@lru_cache(maxsize=1)
def _transparent_weather_tile() -> bytes:
    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    try:
        yield
    finally:
        await runtime.stop()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "A multi-service Gombe State desertification and afforestation intelligence twin combining "
        "Sentinel-2 NDVI, optional Sentinel-1 radar, rainfall/drought history, Global Forest Watch, "
        "FIRMS thermal anomalies, field verification and transparent restoration scenario modelling."
    ),
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def frontend_cache_control(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path.lower()
    if path == "/" or path in PAGES or path.startswith("/lga/") or path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


class RunRequest(BaseModel):
    running: bool


class SpeedRequest(BaseModel):
    speed: float = Field(ge=0.25, le=5.0)


class CorridorRequest(BaseModel):
    coordinates: list[tuple[float, float]] = Field(min_length=2, max_length=200)
    width_cells: int = Field(default=2, ge=1, le=6)


class RouteRequest(BaseModel):
    start: tuple[float, float] | None = None
    end: tuple[float, float] | None = None




class LGAScenarioRequest(BaseModel):
    aridity_pressure: float = Field(default=0.58, ge=0.0, le=1.0)
    grazing_pressure: float = Field(default=0.35, ge=0.0, le=1.0)
    rainfall_support: float = Field(default=0.35, ge=0.0, le=1.0)
    restoration_effort: float = Field(default=0.45, ge=0.0, le=1.0)
    barrier_maintenance: float = Field(default=0.70, ge=0.0, le=1.0)
    steps: int = Field(default=36, ge=6, le=120)


class AdminLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=500)


class TemporalBackfillRequest(BaseModel):
    months: int = Field(default=12, ge=3, le=36)


class FieldObservationRequest(BaseModel):
    observer: str = Field(min_length=2, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    lga: str | None = Field(default=None, max_length=120)
    observation_type: str = Field(min_length=2, max_length=80)
    tree_count: int | None = Field(default=None, ge=0, le=10_000_000)
    survival_percent: float | None = Field(default=None, ge=0, le=100)
    species: str | None = Field(default=None, max_length=200)
    condition: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    photo_url: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObservationStatusRequest(BaseModel):
    status: str = Field(pattern="^(pending|verified|rejected|needs-review)$")


class RestorationProjectRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    organisation: str | None = Field(default=None, max_length=200)
    lga: str | None = Field(default=None, max_length=120)
    status: str = Field(default="planned", pattern="^(planned|active|maintenance|completed|paused|failed)$")
    target_trees: int | None = Field(default=None, ge=0, le=100_000_000)
    planted_trees: int | None = Field(default=None, ge=0, le=100_000_000)
    species: str | None = Field(default=None, max_length=500)
    start_date: str | None = None
    funding_source: str | None = Field(default=None, max_length=300)
    manager: str | None = Field(default=None, max_length=200)
    geometry: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=5000)


class ProjectInspectionRequest(BaseModel):
    inspected_at: str | None = None
    survival_percent: float | None = Field(default=None, ge=0, le=100)
    maintenance_score: float | None = Field(default=None, ge=0, le=100)
    grazing_damage: bool = False
    fire_damage: bool = False
    notes: str | None = Field(default=None, max_length=4000)


PAGES = {
    "/": "index.html",
    "/areas": "areas.html",
    "/weather": "weather.html",
    "/satellite": "satellite.html",
    "/simulation": "simulation.html",
    "/planner": "planner.html",
    "/evidence": "evidence.html",
    "/services": "services.html",
    "/timeline": "timeline.html",
    "/drought": "drought.html",
    "/landcover": "landcover.html",
    "/radar": "radar.html",
    "/restoration": "restoration.html",
    "/ecosystems": "ecosystems.html",
    "/risks": "risks.html",
    "/scenarios": "scenarios.html",
    "/field": "field.html",
    "/projects": "projects.html",
    "/predictions": "predictions.html",
    "/compare": "compare.html",
}


for route, filename in PAGES.items():
    async def page(filename: str = filename) -> FileResponse:
        return FileResponse(STATIC_DIR / filename)
    app.add_api_route(route, page, methods=["GET"], include_in_schema=False)


@app.get("/lga/{slug}", include_in_schema=False)
async def lga_twin_page(slug: str) -> FileResponse:
    try:
        runtime.lga_twins.feature(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown Gombe LGA") from exc
    return FileResponse(STATIC_DIR / "lga-twin.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/static/social-preview.jpg", include_in_schema=False)
async def social_preview() -> Response:
    preview = STATIC_DIR / "social-preview.jpg"
    if preview.exists():
        return FileResponse(preview, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
    return Response(make_social_preview(), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "copernicus_configured": settings.has_copernicus_credentials,
        "gfw_configured": settings.has_gfw_credentials,
        "weather_configured": settings.has_weather_credentials,
        "firms_configured": settings.has_firms_credentials,
        "admin_configured": settings.has_admin_credentials,
        "services": [
            "live twin", "temporal change", "drought", "land cover", "Sentinel-1 radar",
            "restoration suitability", "route optimisation", "carbon", "risk", "field registry",
            "project registry", "scenario comparison", "explainable prediction", "eleven LGA digital twins",
        ],
    }


@app.get("/api/snapshot")
async def snapshot() -> JSONResponse:
    return JSONResponse((await runtime.frame()).model_dump(mode="json"))


@app.get("/api/boundary")
async def boundary() -> dict:
    return runtime.boundary


@app.get("/api/lgas")
async def lgas() -> dict:
    return runtime.lgas


@app.get("/api/northern-lgas")
async def northern_lga_boundaries() -> dict:
    return runtime.northern


@app.get("/api/locations")
async def locations() -> dict:
    return runtime.locations


@app.get("/api/areas")
async def areas() -> list[dict]:
    return await runtime.area_profiles()


@app.get("/api/areas/{slug}")
async def area(slug: str) -> dict:
    try:
        return await runtime.area_profile(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown Gombe LGA") from exc


# ---- Version 5 LGA digital-twin microservices ---------------------------------------

@app.get("/api/lga-twins")
async def lga_twin_catalogue() -> list[dict]:
    return await runtime.lga_twins.catalogue()


@app.get("/api/lga-twins/{slug}/snapshot")
async def lga_twin_snapshot(slug: str) -> dict:
    try:
        return await runtime.lga_twins.snapshot(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown Gombe LGA") from exc


@app.get("/api/lga-twins/{slug}/boundary")
async def lga_twin_boundary(slug: str) -> dict:
    try:
        return await runtime.lga_twins.boundary(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown Gombe LGA") from exc


@app.get("/api/lga-twins/{slug}/textures/{layer}.png")
async def lga_twin_texture(slug: str, layer: str) -> Response:
    if layer not in {"ndvi", "simulation", "landcover", "suitability", "risk"}:
        raise HTTPException(status_code=404, detail="Unknown LGA texture layer")
    try:
        content, version = await runtime.lga_twins.texture(slug, layer)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown Gombe LGA") from exc
    return Response(content, media_type="image/png", headers={"Cache-Control": "no-store", "ETag": f'"lga-{slug}-{layer}-{version}"'})


@app.post("/api/lga-twins/{slug}/scenario")
async def lga_twin_scenario(slug: str, request: LGAScenarioRequest) -> dict:
    try:
        return await runtime.lga_twins.scenario(slug, request.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown Gombe LGA") from exc


@app.get("/api/lga-twins/{slug}/projects")
async def lga_twin_projects(slug: str) -> list[dict]:
    try:
        snapshot = await runtime.lga_twins.snapshot(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown Gombe LGA") from exc
    return snapshot["projects"]


@app.get("/api/lga-twins/{slug}/field-observations")
async def lga_twin_field_observations(slug: str) -> list[dict]:
    try:
        snapshot = await runtime.lga_twins.snapshot(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown Gombe LGA") from exc
    return snapshot["field_observations"]


@app.post("/api/admin/lga-twins/{slug}/refresh-satellite")
async def refresh_lga_satellite(slug: str, authorization: str | None = Header(default=None)) -> dict:
    _require_admin(authorization)
    try:
        data = await runtime.lga_twins.satellite(slug, force=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown Gombe LGA") from exc
    return data.snapshot.model_dump(mode="json")


@app.get("/api/weather")
async def weather() -> dict:
    frame = await runtime.frame()
    return frame.weather.model_dump(mode="json")


@app.get("/api/weather/forecast")
async def weather_forecast() -> dict:
    return (await runtime.weather_forecast()).model_dump(mode="json")


@app.get("/api/weather/tiles/{layer}/{z}/{x}/{y}.png")
async def weather_tile(layer: str, z: int, x: int, y: int) -> Response:
    if not settings.has_weather_credentials:
        return Response(_transparent_weather_tile(), media_type="image/png", headers={"Cache-Control": "public, max-age=300"})
    try:
        content, content_type = await runtime.weather_map_tile(layer, z, x, y)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Weather map tile unavailable: %s", exc)
        return Response(_transparent_weather_tile(), media_type="image/png", headers={"Cache-Control": "no-store"})
    return Response(content, media_type=content_type, headers={"Cache-Control": "public, max-age=300"})


@app.post("/api/weather/refresh")
async def refresh_weather() -> dict:
    return (await runtime.manual_refresh_weather()).model_dump(mode="json")


@app.get("/api/ndvi/grid")
async def ndvi_grid() -> dict:
    return await runtime.get_ndvi_grid()


@app.get("/api/ndvi/texture.png")
async def ndvi_texture() -> Response:
    content, version = await runtime.ndvi_texture()
    return Response(content, media_type="image/png", headers={"Cache-Control": "no-store", "ETag": f'"ndvi-{version}"'})


@app.get("/api/simulation/texture.png")
async def simulation_texture() -> Response:
    content, version = await runtime.simulation_texture()
    return Response(content, media_type="image/png", headers={"Cache-Control": "no-store", "ETag": f'"simulation-{version}"'})


@app.get("/api/simulation/trees")
async def trees() -> dict:
    return await runtime.trees()


@app.get("/api/history")
async def history() -> list[dict]:
    return await runtime.history()


@app.post("/api/simulation/scenario")
async def set_scenario(parameters: ScenarioParameters) -> dict:
    return (await runtime.set_scenario(parameters)).model_dump(mode="json")


@app.post("/api/simulation/run")
async def set_running(request: RunRequest) -> dict:
    return (await runtime.set_running(request.running)).model_dump(mode="json")


@app.post("/api/simulation/speed")
async def set_speed(request: SpeedRequest) -> dict:
    return (await runtime.set_speed(request.speed)).model_dump(mode="json")


@app.post("/api/simulation/reset")
async def reset_simulation() -> dict:
    return (await runtime.reset_simulation()).model_dump(mode="json")


@app.post("/api/planner/corridor")
async def plant_corridor(request: CorridorRequest) -> dict:
    try:
        return await runtime.plant_corridor(request.coordinates, request.width_cells)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/planner/corridors")
async def clear_corridors() -> dict:
    return await runtime.clear_corridors()


# ---- Version 4 intelligence services -------------------------------------------------


@app.get("/api/intelligence/summary")
async def intelligence_summary() -> dict:
    return await runtime.dashboard_intelligence()


@app.get("/api/temporal")
async def temporal() -> dict:
    return await runtime.temporal()


@app.get("/api/rainfall")
async def rainfall() -> dict:
    return await runtime.rainfall()


@app.get("/api/radar")
async def radar() -> dict:
    return await runtime.radar()


@app.get("/api/radar/texture.png")
async def radar_texture() -> Response:
    content, version = await runtime.radar_service.texture()
    return Response(content, media_type="image/png", headers={"Cache-Control": "no-store", "ETag": f'"radar-{version}"'})


@app.get("/api/landcover")
async def landcover() -> dict:
    return await runtime.landcover()


@app.get("/api/landcover/texture.png")
async def landcover_texture() -> Response:
    await runtime.landcover()
    content, version = runtime.intelligence.landcover_texture()
    return Response(content, media_type="image/png", headers={"Cache-Control": "no-store", "ETag": f'"landcover-{version}"'})


@app.get("/api/suitability")
async def suitability() -> dict:
    return await runtime.suitability()


@app.get("/api/suitability/texture.png")
async def suitability_texture() -> Response:
    await runtime.suitability()
    content, version = runtime.intelligence.suitability_texture()
    return Response(content, media_type="image/png", headers={"Cache-Control": "no-store", "ETag": f'"suitability-{version}"'})


@app.post("/api/suitability/routes")
async def optimise_routes(request: RouteRequest) -> dict:
    return await runtime.routes(request.start, request.end)


@app.get("/api/carbon")
async def carbon() -> dict:
    return await runtime.carbon()


@app.get("/api/risks")
async def risks() -> dict:
    return await runtime.risks()


@app.get("/api/risks/texture.png")
async def risk_texture() -> Response:
    await runtime.risks()
    content, version = runtime.intelligence.risk_texture()
    return Response(content, media_type="image/png", headers={"Cache-Control": "no-store", "ETag": f'"risk-{version}"'})


@app.get("/api/fires")
async def fires() -> dict:
    return await runtime.fires()


@app.get("/api/scenarios")
async def scenarios() -> dict:
    return await runtime.scenarios()


@app.get("/api/alerts")
async def alerts() -> list[dict]:
    return await runtime.alerts()


@app.get("/api/predictions/status")
async def prediction_status() -> dict:
    return await runtime.prediction_status()


@app.get("/api/predictions/forecast")
async def prediction_forecast(months: int = Query(default=6, ge=1, le=24)) -> dict:
    return await runtime.prediction_forecast(months)


# ---- Protected administration --------------------------------------------------------


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _require_admin(authorization: str | None) -> str:
    token = _bearer_token(authorization)
    if not runtime.security.verify_token(token):
        raise HTTPException(status_code=401, detail="Valid administrator bearer token required")
    assert token is not None
    return token


@app.post("/api/admin/login")
async def admin_login(request: AdminLoginRequest, http_request: Request) -> dict:
    if not settings.has_admin_credentials:
        raise HTTPException(status_code=503, detail="Administrator credentials are not configured")
    client = http_request.client.host if http_request.client else "unknown"
    result = runtime.security.login(request.password, client)
    if result is None:
        raise HTTPException(status_code=401, detail="Authentication failed or temporarily blocked")
    return {"token": result.token, "expires_at": result.expires_at}


@app.post("/api/admin/logout")
async def admin_logout(authorization: str | None = Header(default=None)) -> dict:
    token = _require_admin(authorization)
    runtime.security.revoke(token)
    return {"status": "ok"}


@app.post("/api/admin/predictions/retrain")
async def retrain_predictions(authorization: str | None = Header(default=None)) -> dict:
    _require_admin(authorization)
    try:
        return await runtime.retrain_prediction()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/temporal/backfill")
async def temporal_backfill(request: TemporalBackfillRequest, authorization: str | None = Header(default=None)) -> dict:
    _require_admin(authorization)
    try:
        return await runtime.backfill_temporal(request.months)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---- Field verification and restoration registry ------------------------------------


@app.get("/api/field/observations")
async def field_observations(limit: int = Query(default=200, ge=1, le=1000)) -> list[dict]:
    return runtime.store.list_observations(limit)


@app.post("/api/field/observations")
async def create_field_observation(request: FieldObservationRequest, authorization: str | None = Header(default=None)) -> dict:
    _require_admin(authorization)
    if not runtime.point_in_northern_focus(request.longitude, request.latitude):
        raise HTTPException(status_code=422, detail="Observation coordinate must lie inside a northern Gombe focus LGA")
    return runtime.store.create_observation(request.model_dump())


@app.patch("/api/field/observations/{observation_id}/status")
async def update_field_status(observation_id: int, request: ObservationStatusRequest, authorization: str | None = Header(default=None)) -> dict:
    _require_admin(authorization)
    result = runtime.store.update_observation_status(observation_id, request.status)
    if result is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    return result


@app.get("/api/projects")
async def projects() -> list[dict]:
    return runtime.store.list_projects()


@app.post("/api/projects")
async def create_project(request: RestorationProjectRequest, authorization: str | None = Header(default=None)) -> dict:
    _require_admin(authorization)
    return runtime.store.create_project(request.model_dump())


@app.post("/api/projects/{project_id}/inspections")
async def add_project_inspection(project_id: int, request: ProjectInspectionRequest, authorization: str | None = Header(default=None)) -> dict:
    _require_admin(authorization)
    try:
        return runtime.store.add_inspection(project_id, request.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.get("/api/species-profiles")
async def species_profiles() -> dict:
    return {
        "mode": "expert-configurable-library",
        "profiles": [
            {"name": "Acacia senegal", "native_status": "regional", "drought_tolerance": "high", "livelihood_value": "gum arabic", "verification": "Confirm provenance, soil and community preference locally."},
            {"name": "Faidherbia albida", "native_status": "regional", "drought_tolerance": "moderate-high", "livelihood_value": "agroforestry and shade", "verification": "Confirm water table, spacing and farming-system compatibility."},
            {"name": "Balanites aegyptiaca", "native_status": "regional", "drought_tolerance": "high", "livelihood_value": "food, fodder and restoration", "verification": "Confirm nursery availability and land-user preference."},
            {"name": "Ziziphus mauritiana", "native_status": "regional/naturalised", "drought_tolerance": "high", "livelihood_value": "fruit and shelter", "verification": "Confirm local ecological suitability and management plan."},
        ],
        "limitations": "Species profiles are planning prompts, not prescriptions. A local forestry/ecology assessment is required before planting.",
    }


@app.get("/api/methodology")
async def methodology() -> dict[str, object]:
    return {
        "boundaries": {
            "state": "Gombe State ADM1 from geoBoundaries when available; labelled approximate fallback otherwise.",
            "lgas": "All 11 Gombe LGAs from geoBoundaries ADM2 when available.",
            "northern_focus": ["Dukku", "Funakaye", "Gombe", "Kwami", "Nafada"],
        },
        "observations": {
            "ndvi": "Sentinel-2 L2A cloud-masked NDVI through Copernicus Data Space Process API.",
            "radar": "Optional Sentinel-1 GRD backscatter and radar vegetation index through the same Process API.",
            "weather": "OpenWeather current and forecast data; Open-Meteo historical reanalysis for rainfall/drought screening.",
            "forest": "Global Forest Watch tree-cover-loss context.",
            "fire": "NASA FIRMS thermal anomalies when a map key is configured.",
        },
        "derived_layers": {
            "land_cover": "Transparent NDVI/radar/model classification unless externally prepared Dynamic World statistics are configured.",
            "suitability": "Weighted screening model for restoration planning; not a final site-selection decision.",
            "carbon": "GEDI-calibrated context when configured, otherwise wide-uncertainty scenario screening.",
            "erosion_hydrology": "Process proxies rather than a calibrated catchment model.",
        },
        "simulation": {
            "type": "Continuous-state cellular automaton and multi-scenario experiments.",
            "interpretation": "Scenario outputs and AI predictions are not operational forecasts or field measurements.",
        },
        "governance": {
            "admin": "Protected actions use short-lived bearer tokens created from an administrator password configured only in the deployment environment.",
            "persistence": "SQLite storage is local; Render Free filesystems are ephemeral across restarts and redeploys.",
        },
    }


@app.websocket("/ws/lga/{slug}")
async def lga_live_socket(websocket: WebSocket, slug: str) -> None:
    try:
        runtime.lga_twins.feature(slug)
    except KeyError:
        await websocket.close(code=1008, reason="Unknown Gombe LGA")
        return
    await websocket.accept()
    try:
        while True:
            payload = await runtime.lga_twins.snapshot(slug)
            await websocket.send_json(payload)
            await asyncio.sleep(max(3.0, settings.broadcast_interval_seconds * 3.0))
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("LGA WebSocket closed: %s", exc)
        with suppress(Exception):
            await websocket.close()


@app.websocket("/ws/live")
async def live_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = await runtime.subscribe()
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("WebSocket closed: %s", exc)
    finally:
        runtime.unsubscribe(queue)
