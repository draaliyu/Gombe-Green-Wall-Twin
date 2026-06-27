from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from app.config import Settings
from app.models import (
    GFWSnapshot,
    SatelliteSnapshot,
    ScenarioParameters,
    SimulationSnapshot,
    TwinFrame,
)
from app.services.boundary import NORTHERN_REFERENCE_LOCATIONS, bbox_polygon, fetch_gombe_boundary
from app.services.cellular import DesertificationAutomaton
from app.services.gfw import GFWService
from app.services.insights import build_insights
from app.services.sentinel import SatelliteData, SentinelNDVIService

LOGGER = logging.getLogger("green-wall-twin.runtime")


class TwinRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(
            headers={"User-Agent": "Northern-Gombe-Green-Wall-Twin/1.0"},
            follow_redirects=True,
        )
        self.sentinel = SentinelNDVIService(settings, self.client)
        self.gfw_service = GFWService(settings, self.client)
        self.automaton = DesertificationAutomaton(settings)
        self.boundary: dict[str, Any] = {}
        self.locations = NORTHERN_REFERENCE_LOCATIONS
        self.satellite_data: SatelliteData | None = None
        self.gfw_data: GFWSnapshot | None = None
        self.sequence = 0
        self._tasks: list[asyncio.Task[Any]] = []
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._history: list[dict[str, Any]] = []
        self._history_path = settings.data_dir / "history.json"

    async def start(self) -> None:
        self.boundary = await fetch_gombe_boundary(self.client)
        self.satellite_data = await self.sentinel.initial_data()
        self.automaton.initialise_from_ndvi(self.satellite_data.ndvi, self.satellite_data.valid)
        self.gfw_data = await self.gfw_service.fetch(bbox_polygon(self.settings.aoi_bbox))
        self._load_history()
        await self._record_history(force=True)
        self._tasks = [
            asyncio.create_task(self._simulation_loop(), name="simulation-loop"),
            asyncio.create_task(self._satellite_loop(), name="satellite-loop"),
            asyncio.create_task(self._gfw_loop(), name="gfw-loop"),
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

    async def _simulation_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.simulation_interval_seconds)
            async with self._lock:
                self.automaton.step()

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
            if self.satellite_data is None or self.gfw_data is None:
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
            source_modes = {self.satellite_data.snapshot.mode, self.gfw_data.mode}
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
                simulation=simulation,
                insights=build_insights(self.satellite_data.snapshot, self.gfw_data, metrics),
            )

    async def satellite_snapshot(self) -> SatelliteSnapshot:
        async with self._lock:
            if self.satellite_data is None:
                raise RuntimeError("Satellite service unavailable")
            return self.satellite_data.snapshot

    async def get_ndvi_grid(self) -> dict[str, Any]:
        async with self._lock:
            if self.satellite_data is None:
                raise RuntimeError("Satellite service unavailable")
            ndvi = self.satellite_data.ndvi
            valid = self.satellite_data.valid
            return {
                "width": int(ndvi.shape[1]),
                "height": int(ndvi.shape[0]),
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
        return (await self.frame()).simulation

    async def plant_corridor(self, coordinates: list[tuple[float, float]], width_cells: int) -> dict[str, Any]:
        async with self._lock:
            changed = self.automaton.plant_corridor(coordinates, self.settings.aoi_bbox, width_cells)
            metrics = self.automaton.metrics()
        return {
            "status": "ok",
            "cells_planted": changed,
            "tree_version": self.automaton.tree_version,
            "metrics": metrics.model_dump(),
            "note": "Planted cells are simulation interventions, not verified real-world plantations.",
        }

    async def clear_corridors(self) -> dict[str, Any]:
        async with self._lock:
            self.automaton.clear_barriers()
        return {"status": "ok", "note": "All simulated barrier cells were removed."}

    async def manual_refresh_satellite(self) -> SatelliteSnapshot:
        if not self.settings.has_copernicus_credentials:
            raise RuntimeError("Copernicus credentials are not configured")
        refreshed = await self.sentinel.fetch_live()
        async with self._lock:
            self.satellite_data = refreshed
            self.automaton.assimilate_ndvi(refreshed.ndvi, refreshed.valid)
        await self._record_history(force=True)
        return refreshed.snapshot

    async def manual_refresh_gfw(self) -> GFWSnapshot:
        refreshed = await self.gfw_service.fetch(bbox_polygon(self.settings.aoi_bbox))
        async with self._lock:
            self.gfw_data = refreshed
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
            return self.satellite_data.texture_png, self.satellite_data.snapshot.texture_version

    async def simulation_texture(self) -> tuple[bytes, int]:
        async with self._lock:
            return self.automaton.texture_png, self.automaton.texture_version

    async def trees(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "version": self.automaton.tree_version,
                "features": [tree.model_dump() for tree in self.automaton.trees],
                "note": "Tree geometry is a simulation visualisation; height and health are model states.",
            }

    async def _record_history(self, force: bool = False) -> None:
        frame = await self.frame()
        record = {
            "timestamp": frame.generated_at.isoformat(),
            "ndvi_mean": frame.satellite.stats.mean,
            "ndvi_bare_fraction": frame.satellite.stats.bare_fraction,
            "vegetated_fraction": frame.simulation.metrics.vegetated_fraction,
            "desert_fraction": frame.simulation.metrics.desert_fraction,
            "barrier_fraction": frame.simulation.metrics.barrier_fraction,
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
