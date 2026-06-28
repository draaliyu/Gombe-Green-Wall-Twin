from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import get_settings
from app.models import ScenarioParameters
from app.services.runtime import TwinRuntime
from app.services.texture import make_social_preview

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger("green-wall-twin")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
settings = get_settings()
runtime = TwinRuntime(settings)


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
        "A live Gombe State and northern-focus desertification/afforestation digital twin using "
        "Sentinel-2 NDVI, Global Forest Watch context, current weather forcing and a transparent "
        "cellular-automata restoration scenario model."
    ),
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class RunRequest(BaseModel):
    running: bool


class SpeedRequest(BaseModel):
    speed: float = Field(ge=0.25, le=5.0)


class CorridorRequest(BaseModel):
    coordinates: list[tuple[float, float]] = Field(min_length=2, max_length=200)
    width_cells: int = Field(default=2, ge=1, le=6)


PAGES = {
    "/": "index.html",
    "/areas": "areas.html",
    "/weather": "weather.html",
    "/satellite": "satellite.html",
    "/simulation": "simulation.html",
    "/planner": "planner.html",
    "/evidence": "evidence.html",
}


for route, filename in PAGES.items():
    async def page(filename: str = filename) -> FileResponse:
        return FileResponse(STATIC_DIR / filename)
    app.add_api_route(route, page, methods=["GET"], include_in_schema=False)


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


@app.get("/api/weather")
async def weather() -> dict:
    frame = await runtime.frame()
    return frame.weather.model_dump(mode="json")


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


@app.get("/api/methodology")
async def methodology() -> dict[str, object]:
    return {
        "boundaries": {
            "state": "Gombe State ADM1 from geoBoundaries when available; labelled approximate fallback otherwise.",
            "lgas": "All 11 Gombe LGAs from geoBoundaries ADM2 when available.",
            "northern_focus": ["Dukku", "Funakaye", "Gombe", "Kwami", "Nafada"],
            "note": "The northern focus follows the five LGAs in Gombe North senatorial district; the full state remains visible for context.",
        },
        "ndvi": {
            "formula": "(B08 - B04) / (B08 + B04)",
            "source": "Sentinel-2 L2A through Copernicus Data Space Sentinel Hub Process API",
            "masking": "SCL cloud, cloud-shadow, cirrus, snow/ice and no-data classes are excluded.",
            "interpretation": "NDVI is a spectral greenness indicator; it is not a direct measurement of desertification or tree count.",
        },
        "weather": {
            "source": "OpenWeather current weather API when configured",
            "forcing": "Temperature, humidity, recent rain and wind are converted to bounded moisture and heat-stress signals.",
            "interpretation": "Weather forcing modifies the scenario incrementally; it does not substitute for soil moisture or field measurements.",
        },
        "forest_change": {
            "source": "Global Forest Watch Data API, UMD tree-cover-loss dataset",
            "interpretation": "Tree-cover loss is contextual evidence and does not establish the cause or permanence of land degradation.",
        },
        "simulation": {
            "type": "Continuous-state cellular automaton",
            "drivers": ["NDVI assimilation", "weather forcing", "scenario aridity", "grazing pressure", "restoration effort", "barrier maintenance"],
            "interpretation": "Outputs are scenario experiments, not operational forecasts.",
        },
        "trees": {
            "meaning": "Procedural 3D trees visualise modelled vegetation and planted barrier cells.",
            "limitation": "They are not geolocated observations of individual real trees.",
        },
    }


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
