from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from app.config import Settings
from app.services.enhanced_types import normalise_external_landcover
from app.services.fires import FIRMSService
from app.services.intelligence import IntelligenceEngine
from app.services.lga_twins import LGATwinService
from app.services.prediction import PredictionService
from app.services.radar import Sentinel1RadarService
from app.services.rainfall import RainfallDroughtService
from app.services.runtime import TwinRuntime
from app.services.security import AdminSecurity
from app.services.store import TwinStore

LOGGER = logging.getLogger("green-wall-twin.enhanced-runtime")


class EnhancedTwinRuntime(TwinRuntime):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.rainfall_service = RainfallDroughtService(settings, self.client)
        self.radar_service = Sentinel1RadarService(settings, self.client)
        self.firms_service = FIRMSService(settings, self.client)
        self.intelligence = IntelligenceEngine(settings)
        self.store = TwinStore(settings.database_path)
        self.security = AdminSecurity(settings)
        self.prediction = PredictionService(settings)
        self.rainfall_data: dict[str, Any] = {}
        self.radar_data: dict[str, Any] = {}
        self.fire_data: dict[str, Any] = {}
        self.external_landcover: dict[str, Any] | None = None
        self.external_gedi: dict[str, Any] | None = None
        self._enhanced_tasks: list[asyncio.Task[Any]] = []
        self._temporal_archive_path = settings.data_dir / "sentinel_temporal_archive.json"
        self._temporal_archive: list[dict[str, Any]] = self._load_json_list(self._temporal_archive_path)
        self._latest_landcover: dict[str, Any] | None = None
        self._latest_suitability: dict[str, Any] | None = None
        self._latest_risks: dict[str, Any] | None = None
        self.lga_twins = LGATwinService(self)

    async def start(self) -> None:
        await super().start()
        center = self._north_center()
        self.rainfall_data, self.radar_data, self.fire_data = await asyncio.gather(
            self.rainfall_service.fetch(*center),
            self.radar_service.initial_data(),
            self.firms_service.fetch(),
        )
        self.external_landcover = await self._fetch_optional_json(
            self.settings.dynamic_world_stats_url,
            self.settings.dynamic_world_bearer_token,
        )
        self.external_gedi = await self._fetch_optional_json(
            self.settings.gedi_context_url,
            self.settings.gedi_bearer_token,
        )
        self._enhanced_tasks = [
            asyncio.create_task(self._rainfall_loop(), name="rainfall-loop"),
            asyncio.create_task(self._radar_loop(), name="radar-loop"),
            asyncio.create_task(self._fire_loop(), name="firms-loop"),
        ]
        LOGGER.info("Temporal, drought, radar, fire, registry and prediction services started")

    async def stop(self) -> None:
        for task in self._enhanced_tasks:
            task.cancel()
        for task in self._enhanced_tasks:
            with suppress(asyncio.CancelledError):
                await task
        await super().stop()

    def _north_center(self) -> tuple[float, float]:
        features = self.northern.get("features", [])
        if not features:
            west, south, east, north = self.settings.aoi_bbox
            return (west + east) / 2, (south + north) / 2
        centroids = []
        from app.services.geometry import geometry_centroid
        for feature in features:
            centroids.append(geometry_centroid(feature.get("geometry")))
        return float(np.mean([item[0] for item in centroids])), float(np.mean([item[1] for item in centroids]))

    async def _rainfall_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.rainfall_refresh_seconds)
            try:
                self.rainfall_data = await self.rainfall_service.fetch(*self._north_center())
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Rainfall refresh failed: %s", exc)

    async def _radar_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.radar_refresh_seconds)
            if not self.settings.has_copernicus_credentials:
                continue
            try:
                self.radar_data = await self.radar_service.fetch_live()
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Sentinel-1 refresh failed: %s", exc)

    async def _fire_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.firms_refresh_seconds)
            try:
                self.fire_data = await self.firms_service.fetch()
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("FIRMS refresh failed: %s", exc)

    async def _fetch_optional_json(self, url: str, bearer: str) -> dict[str, Any] | None:
        if not url:
            return None
        headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
        try:
            response = await self.client.get(url, headers=headers, timeout=45.0)
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Optional external evidence unavailable from %s: %s", url, exc)
            return None

    async def rainfall(self) -> dict[str, Any]:
        if not self.rainfall_data:
            self.rainfall_data = await self.rainfall_service.fetch(*self._north_center())
        return self.rainfall_data

    async def radar(self) -> dict[str, Any]:
        if not self.radar_data:
            self.radar_data = await self.radar_service.initial_data()
        return self.radar_data

    async def fires(self) -> dict[str, Any]:
        if not self.fire_data:
            self.fire_data = await self.firms_service.fetch()
        return self.fire_data

    async def temporal(self) -> dict[str, Any]:
        frame = await self.frame()
        story = self.intelligence.temporal_story(
            self._history,
            await self.rainfall(),
            frame.satellite.stats.mean,
            frame.source_mode,
        )
        if self._temporal_archive:
            archive_map = {item["period"]: item for item in self._temporal_archive}
            points = {item["period"]: item for item in story["points"]}
            points.update(archive_map)
            story["points"] = [points[key] for key in sorted(points)]
            story["mode"] = "sentinel_archive_plus_recorded"
            story["note"] = "Protected Sentinel-2 archive mosaics are combined with deployment history and clearly labelled derived gaps."
        return story

    async def landcover(self) -> dict[str, Any]:
        async with self._lock:
            if self.satellite_data is None:
                raise RuntimeError("Satellite data unavailable")
            radar = await self.radar()
            radar_grid = np.asarray(radar.get("grid") or [], dtype=np.float32)
            external = normalise_external_landcover(self.external_landcover)
            self._latest_landcover = self.intelligence.land_cover(
                self.satellite_data.ndvi,
                self.satellite_data.valid,
                radar_grid if radar_grid.size else None,
                self.automaton.state,
                external,
            )
            return self._latest_landcover

    async def suitability(self) -> dict[str, Any]:
        async with self._lock:
            self._latest_suitability = self.intelligence.suitability(
                self.automaton.state,
                self.locations,
                self.settings.aoi_bbox,
                await self.rainfall(),
                await self.fires(),
            )
            return self._latest_suitability

    async def routes(
        self,
        start: tuple[float, float] | None = None,
        end: tuple[float, float] | None = None,
    ) -> dict[str, Any]:
        suitability = await self.suitability()
        grid = np.asarray(suitability["grid"], dtype=np.float32)
        return self.intelligence.optimise_routes(grid, self.settings.aoi_bbox, start, end)

    async def carbon(self) -> dict[str, Any]:
        async with self._lock:
            if self.external_gedi:
                agbd = self.external_gedi.get("agbd_mg_ha") or self.external_gedi.get("mean_agbd")
                uncertainty = self.external_gedi.get("uncertainty_mg_ha") or self.external_gedi.get("standard_error")
                if agbd is not None:
                    self.settings.gedi_reference_agbd_mg_ha = float(agbd)
                    self.settings.gedi_reference_uncertainty_mg_ha = float(uncertainty or 0.0)
            result = self.intelligence.carbon_and_ecosystems(
                self.automaton.state,
                len(self.automaton.trees),
                await self.rainfall(),
            )
            if self.external_gedi:
                result["external_reference"] = self.external_gedi
            return result

    async def risks(self) -> dict[str, Any]:
        frame = await self.frame()
        async with self._lock:
            self._latest_risks = self.intelligence.risk_layers(
                self.automaton.state,
                frame.weather,
                await self.rainfall(),
                await self.fires(),
            )
            return self._latest_risks

    async def scenarios(self) -> dict[str, Any]:
        async with self._lock:
            return self.intelligence.compare_scenarios(self.automaton.state)

    async def alerts(self) -> list[dict[str, Any]]:
        frame = await self.frame()
        return self.intelligence.alerts(
            frame.satellite,
            frame.simulation.metrics,
            frame.weather,
            await self.rainfall(),
            await self.fires(),
            self.store.list_projects(),
        )

    async def prediction_status(self) -> dict[str, Any]:
        return self.prediction.status()

    async def prediction_forecast(self, months: int = 6) -> dict[str, Any]:
        temporal = await self.temporal()
        return self.prediction.forecast(temporal["points"], months)

    async def retrain_prediction(self) -> dict[str, Any]:
        temporal = await self.temporal()
        return self.prediction.train(temporal["points"], temporal["mode"])

    async def backfill_temporal(self, months: int = 12) -> dict[str, Any]:
        if not self.settings.has_copernicus_credentials:
            raise RuntimeError("Copernicus credentials are not configured")
        months = max(3, min(months, 36))
        now = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        records = []
        for offset in range(months, 0, -1):
            year = now.year
            month = now.month - offset
            while month <= 0:
                month += 12
                year -= 1
            start = datetime(year, month, 1, tzinfo=timezone.utc)
            next_year = year + (1 if month == 12 else 0)
            next_month = 1 if month == 12 else month + 1
            end = datetime(next_year, next_month, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
            try:
                record = await self.sentinel.fetch_window_statistics(start, end)
                records.append(record)
            except Exception as exc:  # noqa: BLE001
                records.append({"period": start.strftime("%Y-%m"), "mode": "unavailable", "error": type(exc).__name__})
            await asyncio.sleep(0.15)
        successful = [item for item in records if item.get("ndvi") is not None]
        archive = {item["period"]: item for item in self._temporal_archive}
        archive.update({item["period"]: item for item in successful})
        self._temporal_archive = [archive[key] for key in sorted(archive)]
        self._temporal_archive_path.write_text(json.dumps(self._temporal_archive, indent=2), encoding="utf-8")
        return {"requested_months": months, "successful": len(successful), "records": records}

    async def dashboard_intelligence(self) -> dict[str, Any]:
        temporal, rainfall, radar, fire, carbon, risks, alerts = await asyncio.gather(
            self.temporal(), self.rainfall(), self.radar(), self.fires(), self.carbon(), self.risks(), self.alerts()
        )
        return {
            "temporal": {"trend": temporal["trend"], "change": temporal["year_on_year_ndvi_change"], "mode": temporal["mode"]},
            "drought": rainfall.get("drought_screen"),
            "radar": {"mean_rvi": radar.get("mean_rvi"), "mode": radar.get("mode")},
            "fire": {"count": fire.get("hotspot_count"), "total_frp_mw": fire.get("total_frp_mw"), "mode": fire.get("mode")},
            "carbon": {"agbd": carbon.get("aboveground_biomass_density_mg_ha"), "carbon_t": carbon.get("estimated_total_carbon_t"), "mode": carbon.get("mode")},
            "risks": {"wind_erosion": risks.get("wind_erosion_mean"), "runoff": risks.get("runoff_mean"), "combined": risks.get("combined_risk_mean")},
            "alerts": alerts,
            "projects": len(self.store.list_projects()),
            "field_observations": len(self.store.list_observations()),
        }

    def _load_json_list(self, path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except (json.JSONDecodeError, OSError):
            return []
