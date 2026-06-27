from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import get_settings
from app.models import ScenarioParameters
from app.services.runtime import TwinRuntime
from app.services.texture import make_social_preview

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
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
        "A live Sentinel-2 NDVI and Global Forest Watch digital twin with a cellular-automata "
        "desertification/afforestation scenario model for northern Gombe State."
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


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/satellite", include_in_schema=False)
async def satellite_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "satellite.html")


@app.get("/simulation", include_in_schema=False)
async def simulation_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "simulation.html")


@app.get("/planner", include_in_schema=False)
async def planner_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "planner.html")


@app.get("/evidence", include_in_schema=False)
async def evidence_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "evidence.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/static/social-preview.jpg", include_in_schema=False)
async def social_preview() -> Response:
    return Response(make_social_preview(), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "copernicus_configured": settings.has_copernicus_credentials,
        "gfw_configured": settings.has_gfw_credentials,
    }


@app.get("/api/snapshot")
async def snapshot() -> JSONResponse:
    return JSONResponse((await runtime.frame()).model_dump(mode="json"))


@app.get("/api/boundary")
async def boundary() -> dict:
    return runtime.boundary


@app.get("/api/locations")
async def locations() -> dict:
    return runtime.locations


@app.get("/api/ndvi/grid")
async def ndvi_grid() -> dict:
    return await runtime.get_ndvi_grid()


@app.get("/api/ndvi/texture.png")
async def ndvi_texture() -> Response:
    content, version = await runtime.ndvi_texture()
    return Response(
        content,
        media_type="image/png",
        headers={"Cache-Control": "no-store", "ETag": f'"ndvi-{version}"'},
    )


@app.get("/api/simulation/texture.png")
async def simulation_texture() -> Response:
    content, version = await runtime.simulation_texture()
    return Response(
        content,
        media_type="image/png",
        headers={"Cache-Control": "no-store", "ETag": f'"simulation-{version}"'},
    )


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
    west, south, east, north = settings.aoi_bbox
    for longitude, latitude in request.coordinates:
        if not (west <= longitude <= east and south <= latitude <= north):
            raise HTTPException(status_code=422, detail="All corridor points must lie inside the configured northern Gombe AOI")
    return await runtime.plant_corridor(request.coordinates, request.width_cells)


@app.delete("/api/planner/corridors")
async def clear_corridors() -> dict:
    return await runtime.clear_corridors()


@app.get("/api/methodology")
async def methodology() -> dict[str, object]:
    return {
        "ndvi": {
            "formula": "(B08 - B04) / (B08 + B04)",
            "source": "Sentinel-2 L2A through Copernicus Data Space Sentinel Hub Process API",
            "masking": "SCL cloud, cloud-shadow, cirrus, snow/ice and no-data classes are excluded.",
            "interpretation": "NDVI is a spectral greenness indicator; it is not a direct measurement of desertification or tree count.",
        },
        "forest_change": {
            "source": "Global Forest Watch Data API, UMD tree-cover-loss dataset",
            "interpretation": "Tree-cover loss is contextual evidence and does not establish the cause or permanence of land degradation.",
        },
        "simulation": {
            "type": "Continuous-state cellular automaton",
            "drivers": ["NDVI assimilation", "scenario aridity", "grazing pressure", "rainfall support", "restoration effort", "barrier maintenance"],
            "interpretation": "Outputs are scenario experiments, not operational forecasts.",
        },
        "thresholds": {
            "bare_or_very_sparse": "NDVI < 0.15",
            "sparse": "0.15 ≤ NDVI < 0.30",
            "moderate": "0.30 ≤ NDVI < 0.50",
            "dense": "NDVI ≥ 0.50",
            "note": "These are display classes for this demonstrator and require local calibration before operational use.",
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
