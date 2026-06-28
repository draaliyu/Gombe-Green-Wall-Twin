from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any

import httpx
import numpy as np

from app.config import Settings
from app.models import GFWSnapshot, ScenarioParameters, SimulationSnapshot, TwinFrame, WeatherSnapshot
from app.services.boundary import (
    bbox_polygon,
    fetch_gombe_boundaries,
    location_points,
    northern_lgas,
)
from app.services.cellular import DesertificationAutomaton
from app.services.geometry import (
    collection_bounds,
    feature_name,
    geometry_centroid,
    point_in_geometry,
    slugify,
)
from app.services.gfw import GFWService
from app.services.insights import build_insights
from app.services.sentinel import SatelliteData, SentinelNDVIService
from app.services.texture import mask_texture_to_features
from app.services.weather import WeatherService

LOGGER = logging.getLogger("green-wall-twin.runtime")


class TwinRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(
            headers={"User-Agent": "Gombe-Green-Wall-Twin/2.0"},
            follow_redirects=True,
        )
        self.sentinel = SentinelNDVIService(settings, self.client)
        self.gfw_service = GFWService(settings, self.client)
        self.weather_service = WeatherService(settings, self.client)
        self.automaton = DesertificationAutomaton(settings)
        self.boundary: dict[str, Any] = {}
        self.lgas: dict[str, Any] = {}
        self.northern: dict[str, Any] = {}
        self.locations: dict[str, Any] = {}
        self.satellite_data: SatelliteData | None = None
        self.gfw_data: GFWSnapshot | None = None
        self.weather_data: WeatherSnapshot | None = None
        self.sequence = 0
        self._tasks: list[asyncio.Task[Any]] = []
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._history: list[dict[str, Any]] = []
        self._history_path = settings.data_dir / "history.json"
        self._masked_ndvi_cache: tuple[int, bytes] | None = None
        self._masked_simulation_cache: tuple[int, bytes] | None = None
        self.corridor_revision = 0

    async def start(self) -> None:
        self.boundary, self.lgas = await fetch_gombe_boundaries(self.client)
        self.northern = northern_lgas(self.lgas)
        self.locations = location_points(self.lgas)
        self.satellite_data = await self.sentinel.initial_data()
        self.automaton.initialise_from_ndvi(self.satellite_data.ndvi, self.satellite_data.valid)
        self.gfw_data = await self.gfw_service.fetch(bbox_polygon(self.settings.aoi_bbox))
        north_bounds = collection_bounds(self.northern)
        north_center = ((north_bounds[0] + north_bounds[2]) / 2, (north_bounds[1] + north_bounds[3]) / 2)
        self.weather_data = await self.weather_service.fetch(*north_center, "Northern Gombe")
        self._apply_weather_forcing(self.weather_data)
        self._load_history()
        await self._record_history(force=True)
        self._tasks = [
            asyncio.create_task(self._simulation_loop(), name="simulation-loop"),
            asyncio.create_task(self._satellite_loop(), name="satellite-loop"),
            asyncio.create_task(self._gfw_loop(), name="gfw-loop"),
            asyncio.create_task(self._weather_loop(), name="weather-loop"),
            asyncio.create_task(self._broadcast_loop(), name="broadcast-loop"),
            asyncio.create_task(self._history_loop(), name="history-loop"),
        ]
        LOGGER.info("Digital twin runtime started")

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        await self.client.aclose()
        LOGGER.info("Digital twin runtime stopped")

    def _apply_weather_forcing(self, weather: WeatherSnapshot) -> None:
        self.automaton.set_weather_forcing(
            weather.temperature_c,
            weather.humidity_percent,
            weather.rain_1h_mm,
            weather.wind_speed_mps,
        )

    async def _simulation_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.simulation_interval_seconds)
            async with self._lock:
                self.automaton.step()
                self._masked_simulation_cache = None

    async def _satellite_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.satellite_refresh_seconds)
            if not self.settings.has_copernicus_credentials:
                continue
            try:
                refreshed = await self.sentinel.fetch_live()
                async with self._lock:
                    self.satellite_data = refreshed
                    self.automaton.assimilate_ndvi(refreshed.ndvi, refreshed.valid)
                    self._masked_ndvi_cache = None
                    self._masked_simulation_cache = None
                LOGGER.info("Refreshed Sentinel-2 NDVI")
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Scheduled Sentinel-2 refresh failed: %s", exc)

    async def _gfw_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.gfw_refresh_seconds)
            refreshed = await self.gfw_service.fetch(bbox_polygon(self.settings.aoi_bbox))
            async with self._lock:
                self.gfw_data = refreshed
            LOGGER.info("Refreshed Global Forest Watch context")

    async def _weather_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.weather_refresh_seconds)
            bounds = collection_bounds(self.northern)
            center = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
            refreshed = await self.weather_service.fetch(*center, "Northern Gombe")
            async with self._lock:
                self.weather_data = refreshed
                self._apply_weather_forcing(refreshed)
            LOGGER.info("Refreshed weather forcing")

    async def _broadcast_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.broadcast_interval_seconds)
            payload = (await self.frame()).model_dump(mode="json")
            dead: list[asyncio.Queue[dict[str, Any]]] = []
            for queue in list(self._subscribers):
                try:
                    if queue.full():
                        queue.get_nowait()
                    queue.put_nowait(payload)
                except Exception:  # noqa: BLE001
                    dead.append(queue)
            for queue in dead:
                self._subscribers.discard(queue)

    async def _history_loop(self) -> None:
        while True:
            await asyncio.sleep(300)
            await self._record_history()

    async def frame(self) -> TwinFrame:
        async with self._lock:
            if self.satellite_data is None or self.gfw_data is None or self.weather_data is None:
                raise RuntimeError("Twin runtime has not started")
            self.sequence += 1
            metrics = self.automaton.metrics()
            simulation = SimulationSnapshot(
                running=self.automaton.running,
                speed=self.automaton.speed,
                parameters=self.automaton.parameters,
                metrics=metrics,
                texture_version=self.automaton.texture_version,
                tree_version=self.automaton.tree_version,
            )
            source_modes = {self.satellite_data.snapshot.mode, self.gfw_data.mode, self.weather_data.mode}
            if source_modes == {"live"}:
                source_mode = "live"
            elif source_modes == {"demo"}:
                source_mode = "demo"
            else:
                source_mode = "mixed"
            return TwinFrame(
                sequence=self.sequence,
                generated_at=datetime.now(timezone.utc),
                source_mode=source_mode,
                satellite=self.satellite_data.snapshot,
                gfw=self.gfw_data,
                weather=self.weather_data,
                simulation=simulation,
                insights=build_insights(
                    self.satellite_data.snapshot,
                    self.gfw_data,
                    self.weather_data,
                    metrics,
                ),
            )

    async def get_ndvi_grid(self) -> dict[str, Any]:
        async with self._lock:
            if self.satellite_data is None:
                raise RuntimeError("Satellite service unavailable")
            ndvi = self.satellite_data.ndvi
            valid = self.satellite_data.valid
            return {
                "width": int(ndvi.shape[1]),
                "height": int(ndvi.shape[0]),
                "bbox": list(self.settings.aoi_bbox),
                "values": np.where(valid, ndvi, np.nan).round(4).tolist(),
                "mode": self.satellite_data.snapshot.mode,
                "texture_version": self.satellite_data.snapshot.texture_version,
            }

    async def set_scenario(self, parameters: ScenarioParameters) -> SimulationSnapshot:
        async with self._lock:
            self.automaton.set_parameters(parameters)
        return (await self.frame()).simulation

    async def set_running(self, running: bool) -> SimulationSnapshot:
        async with self._lock:
            self.automaton.set_running(running)
        return (await self.frame()).simulation

    async def set_speed(self, speed: float) -> SimulationSnapshot:
        async with self._lock:
            self.automaton.set_speed(speed)
        return (await self.frame()).simulation

    async def reset_simulation(self) -> SimulationSnapshot:
        async with self._lock:
            if self.satellite_data is None:
                raise RuntimeError("Satellite service unavailable")
            self.automaton.initialise_from_ndvi(self.satellite_data.ndvi, self.satellite_data.valid)
            if self.weather_data is not None:
                self._apply_weather_forcing(self.weather_data)
            self.corridor_revision += 1
            self._masked_simulation_cache = None
        return (await self.frame()).simulation

    def point_in_northern_focus(self, longitude: float, latitude: float) -> bool:
        return any(
            point_in_geometry(longitude, latitude, feature.get("geometry"))
            for feature in self.northern.get("features", [])
        )

    async def plant_corridor(self, coordinates: list[tuple[float, float]], width_cells: int) -> dict[str, Any]:
        if not all(self.point_in_northern_focus(longitude, latitude) for longitude, latitude in coordinates):
            raise ValueError("All corridor points must lie inside a northern Gombe focus LGA")
        async with self._lock:
            changed = self.automaton.plant_corridor(coordinates, self.settings.aoi_bbox, width_cells)
            metrics = self.automaton.metrics()
            self.corridor_revision += 1
            self._masked_simulation_cache = None
        return {
            "status": "ok",
            "cells_planted": changed,
            "tree_version": self.automaton.tree_version,
            "corridor_revision": self.corridor_revision,
            "metrics": metrics.model_dump(),
            "note": (
                "The committed corridor is a temporary in-memory scenario intervention. "
                "The drawing draft has not been stored and should clear after submission or page refresh."
            ),
        }

    async def clear_corridors(self) -> dict[str, Any]:
        async with self._lock:
            self.automaton.clear_barriers()
            self.corridor_revision += 1
            self._masked_simulation_cache = None
        return {
            "status": "ok",
            "corridor_revision": self.corridor_revision,
            "note": "All committed simulated barrier cells were removed from the current runtime scenario.",
        }

    async def manual_refresh_satellite(self):
        if not self.settings.has_copernicus_credentials:
            raise RuntimeError("Copernicus credentials are not configured")
        refreshed = await self.sentinel.fetch_live()
        async with self._lock:
            self.satellite_data = refreshed
            self.automaton.assimilate_ndvi(refreshed.ndvi, refreshed.valid)
            self._masked_ndvi_cache = None
            self._masked_simulation_cache = None
        await self._record_history(force=True)
        return refreshed.snapshot

    async def manual_refresh_gfw(self) -> GFWSnapshot:
        refreshed = await self.gfw_service.fetch(bbox_polygon(self.settings.aoi_bbox))
        async with self._lock:
            self.gfw_data = refreshed
        return refreshed

    async def manual_refresh_weather(self) -> WeatherSnapshot:
        bounds = collection_bounds(self.northern)
        center = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
        refreshed = await self.weather_service.fetch(*center, "Northern Gombe")
        async with self._lock:
            self.weather_data = refreshed
            self._apply_weather_forcing(refreshed)
        return refreshed

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=2)
        self._subscribers.add(queue)
        queue.put_nowait((await self.frame()).model_dump(mode="json"))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    async def ndvi_texture(self) -> tuple[bytes, int]:
        async with self._lock:
            if self.satellite_data is None:
                raise RuntimeError("Satellite texture unavailable")
            version = self.satellite_data.snapshot.texture_version
            if self._masked_ndvi_cache and self._masked_ndvi_cache[0] == version:
                return self._masked_ndvi_cache[1], version
            masked = mask_texture_to_features(
                self.satellite_data.texture_png,
                self.northern,
                self.settings.aoi_bbox,
            )
            self._masked_ndvi_cache = (version, masked)
            return masked, version

    async def simulation_texture(self) -> tuple[bytes, int]:
        async with self._lock:
            version = self.automaton.texture_version
            if self._masked_simulation_cache and self._masked_simulation_cache[0] == version:
                return self._masked_simulation_cache[1], version
            masked = mask_texture_to_features(
                self.automaton.texture_png,
                self.northern,
                self.settings.aoi_bbox,
            )
            self._masked_simulation_cache = (version, masked)
            return masked, version

    async def trees(self) -> dict[str, Any]:
        async with self._lock:
            trees = [
                tree.model_dump()
                for tree in self.automaton.trees
                if self.point_in_northern_focus(tree.longitude, tree.latitude)
            ]
            return {
                "version": self.automaton.tree_version,
                "features": trees,
                "weather": {
                    "wind_speed_mps": self.weather_data.wind_speed_mps if self.weather_data else 0.0,
                    "wind_direction_deg": self.weather_data.wind_direction_deg if self.weather_data else 0.0,
                },
                "note": (
                    "Procedural tree geometry is driven by the modelled vegetation and planted-barrier state; "
                    "it is not an inventory of individual real trees."
                ),
            }

    def _find_area(self, slug: str) -> dict[str, Any] | None:
        for feature in self.lgas.get("features", []):
            properties = feature.get("properties") or {}
            if properties.get("slug") == slug or slugify(feature_name(feature)) == slug:
                return feature
        return None

    async def area_profiles(self) -> list[dict[str, Any]]:
        profiles = []
        for feature in self.lgas.get("features", []):
            properties = feature.get("properties") or {}
            centroid = geometry_centroid(feature.get("geometry"))
            profiles.append({
                "slug": properties.get("slug") or slugify(feature_name(feature)),
                "name": properties.get("name") or feature_name(feature),
                "northern_focus": bool(properties.get("northern_focus")),
                "centroid": {"longitude": centroid[0], "latitude": centroid[1]},
                "boundary_source": properties.get("source", "unknown"),
            })
        return profiles

    async def area_profile(self, slug: str) -> dict[str, Any]:
        feature = self._find_area(slug)
        if feature is None:
            raise KeyError(slug)
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry")
        centroid = geometry_centroid(geometry)
        weather = await self.weather_service.fetch(*centroid, str(properties.get("name") or feature_name(feature)))
        async with self._lock:
            if self.satellite_data is None or self.gfw_data is None:
                raise RuntimeError("Twin data unavailable")
            ndvi_values = self._values_inside_geometry(
                self.satellite_data.ndvi,
                self.satellite_data.valid,
                geometry,
                self.settings.aoi_bbox,
            )
            simulation_values = self._simulation_inside_geometry(geometry)
            ndvi_mean = float(np.mean(ndvi_values)) if ndvi_values.size else None
            ndvi_low = float(np.mean(ndvi_values < 0.15)) if ndvi_values.size else None
            ndvi_dense = float(np.mean(ndvi_values >= 0.50)) if ndvi_values.size else None
            vegetation = simulation_values[0]
            desert = simulation_values[1]
            barrier = simulation_values[2]
            simulated_vegetated = float(np.mean(vegetation > 0.38)) if vegetation.size else None
            simulated_desert = float(np.mean(desert > 0.60)) if desert.size else None
            simulated_barrier = float(np.mean(barrier > 0.08)) if barrier.size else None
            interpretation = self._area_interpretation(
                str(properties.get("name") or feature_name(feature)),
                ndvi_mean,
                ndvi_low,
                weather,
                simulated_desert,
                simulated_barrier,
            )
            return {
                "slug": properties.get("slug") or slug,
                "name": properties.get("name") or feature_name(feature),
                "northern_focus": bool(properties.get("northern_focus")),
                "boundary_source": properties.get("source", "unknown"),
                "centroid": {"longitude": centroid[0], "latitude": centroid[1]},
                "satellite": {
                    "mode": self.satellite_data.snapshot.mode,
                    "mean_ndvi": round(ndvi_mean, 4) if ndvi_mean is not None else None,
                    "bare_fraction": round(ndvi_low, 4) if ndvi_low is not None else None,
                    "dense_fraction": round(ndvi_dense, 4) if ndvi_dense is not None else None,
                    "observation_window_start": self.satellite_data.snapshot.observation_window_start.isoformat(),
                    "observation_window_end": self.satellite_data.snapshot.observation_window_end.isoformat(),
                    "note": "Area statistics are aggregated from valid Sentinel-2 pixels that fall inside the LGA geometry.",
                },
                "weather": weather.model_dump(mode="json"),
                "simulation": {
                    "vegetated_fraction": round(simulated_vegetated, 4) if simulated_vegetated is not None else None,
                    "desert_fraction": round(simulated_desert, 4) if simulated_desert is not None else None,
                    "barrier_fraction": round(simulated_barrier, 4) if simulated_barrier is not None else None,
                    "tick": self.automaton.tick,
                    "note": "These values are scenario-model outputs, not measured land degradation.",
                },
                "forest_context": {
                    "mode": self.gfw_data.mode,
                    "dataset": self.gfw_data.dataset,
                    "queried_aoi_cumulative_loss_ha": self.gfw_data.cumulative_loss_ha,
                    "note": "The current GFW query covers the northern analysis area and is contextual, not LGA-specific attribution.",
                },
                "interpretation": interpretation,
            }

    def _values_inside_geometry(
        self,
        values: np.ndarray,
        valid: np.ndarray,
        geometry: dict[str, Any],
        bbox: tuple[float, float, float, float],
    ) -> np.ndarray:
        west, south, east, north = bbox
        height, width = values.shape
        selected: list[float] = []
        for row in range(height):
            latitude = north - (row + 0.5) / height * (north - south)
            for col in range(width):
                if not bool(valid[row, col]):
                    continue
                longitude = west + (col + 0.5) / width * (east - west)
                if point_in_geometry(longitude, latitude, geometry):
                    selected.append(float(values[row, col]))
        return np.asarray(selected, dtype=np.float32)

    def _simulation_inside_geometry(self, geometry: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        west, south, east, north = self.settings.aoi_bbox
        height, width = self.automaton.state.vegetation.shape
        rows: list[int] = []
        cols: list[int] = []
        for row in range(height):
            latitude = north - (row + 0.5) / height * (north - south)
            for col in range(width):
                longitude = west + (col + 0.5) / width * (east - west)
                if point_in_geometry(longitude, latitude, geometry):
                    rows.append(row)
                    cols.append(col)
        if not rows:
            empty = np.asarray([], dtype=np.float32)
            return empty, empty, empty
        index = (np.asarray(rows), np.asarray(cols))
        return (
            self.automaton.state.vegetation[index],
            self.automaton.state.desert[index],
            self.automaton.state.barrier[index],
        )

    @staticmethod
    def _area_interpretation(
        name: str,
        ndvi_mean: float | None,
        bare_fraction: float | None,
        weather: WeatherSnapshot,
        desert_fraction: float | None,
        barrier_fraction: float | None,
    ) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        if ndvi_mean is None:
            items.append({"title": "Vegetation evidence", "body": "No valid NDVI pixels intersected the available LGA geometry and analysis grid."})
        else:
            class_text = "very sparse" if ndvi_mean < 0.15 else "sparse" if ndvi_mean < 0.30 else "moderate" if ndvi_mean < 0.50 else "strong"
            items.append({
                "title": "Observed greenness",
                "body": f"The valid satellite pixels over {name} have mean NDVI {ndvi_mean:.2f}, corresponding to the platform's {class_text} greenness display class. {(bare_fraction or 0) * 100:.1f}% of sampled pixels are below 0.15.",
            })
        moisture_signal = "supportive" if weather.rain_1h_mm > 0 or weather.humidity_percent >= 65 else "limited" if weather.humidity_percent < 35 else "mixed"
        items.append({
            "title": "Current weather forcing",
            "body": (
                f"Weather support is {moisture_signal}: {weather.temperature_c:.1f}°C, {weather.humidity_percent:.0f}% humidity, "
                f"{weather.rain_1h_mm:.1f} mm rain in the reported hour and wind {weather.wind_speed_mps:.1f} m/s from {weather.wind_direction_cardinal}. "
                "These values influence the scenario's moisture and heat-stress forcing but do not replace soil or field measurements."
            ),
        })
        if desert_fraction is not None:
            items.append({
                "title": "Scenario trajectory",
                "body": (
                    f"The current cellular scenario classifies {desert_fraction * 100:.1f}% of intersecting cells as high desert pressure. "
                    f"Committed tree barriers occupy {(barrier_fraction or 0) * 100:.2f}% of cells. This is a model experiment, not an observed desert boundary."
                ),
            })
        return items

    async def _record_history(self, force: bool = False) -> None:
        frame = await self.frame()
        record = {
            "timestamp": frame.generated_at.isoformat(),
            "ndvi_mean": frame.satellite.stats.mean,
            "ndvi_bare_fraction": frame.satellite.stats.bare_fraction,
            "vegetated_fraction": frame.simulation.metrics.vegetated_fraction,
            "desert_fraction": frame.simulation.metrics.desert_fraction,
            "barrier_fraction": frame.simulation.metrics.barrier_fraction,
            "temperature_c": frame.weather.temperature_c,
            "rain_1h_mm": frame.weather.rain_1h_mm,
            "source_mode": frame.source_mode,
        }
        if force or not self._history or self._history[-1]["timestamp"] != record["timestamp"]:
            self._history.append(record)
            self._history = self._history[-800:]
            self._history_path.write_text(json.dumps(self._history, indent=2), encoding="utf-8")

    def _load_history(self) -> None:
        if not self._history_path.exists():
            return
        try:
            data = json.loads(self._history_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._history = data[-800:]
        except (json.JSONDecodeError, OSError):
            self._history = []

    async def history(self) -> list[dict[str, Any]]:
        return list(self._history)
