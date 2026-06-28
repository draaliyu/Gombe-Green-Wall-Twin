from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

import numpy as np
from PIL import Image

from app.services.geometry import (
    collection_bounds,
    feature_name,
    geometry_centroid,
    haversine_km,
    iter_polygons,
    point_in_geometry,
    slugify,
)
from app.models import SatelliteSnapshot
from app.services.sentinel import SatelliteData, calculate_stats, generate_demo_ndvi
from app.services.texture import mask_texture_to_features, ndvi_to_texture, simulation_to_texture


@dataclass(slots=True)
class CachedLGAData:
    satellite: SatelliteData
    fetched_at: datetime


class LGATwinService:
    """Scoped service facade for the eleven Gombe LGA digital twins.

    Each LGA receives a stable route and a dedicated API bundle. Observed,
    contextual and scenario-derived values are deliberately separated in the
    returned payload so a polished local twin does not imply unavailable local
    measurements.
    """

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self._satellite_cache: dict[str, CachedLGAData] = {}
        self._cache_lock = asyncio.Lock()
        self._texture_cache: dict[tuple[str, str, int], bytes] = {}

    def feature(self, slug: str) -> dict[str, Any]:
        feature = self.runtime._find_area(slug)  # existing canonical resolver
        if feature is None:
            raise KeyError(slug)
        return feature

    def canonical_slug(self, slug: str) -> str:
        feature = self.feature(slug)
        props = feature.get("properties") or {}
        return str(props.get("slug") or slugify(feature_name(feature)))

    async def catalogue(self) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for feature in self.runtime.lgas.get("features", []):
            props = feature.get("properties") or {}
            name = str(props.get("name") or feature_name(feature))
            slug = str(props.get("slug") or slugify(name))
            centroid = geometry_centroid(feature.get("geometry"))
            output.append({
                "slug": slug,
                "name": name,
                "route": f"/lga/{slug}",
                "api": f"/api/lga-twins/{slug}/snapshot",
                "northern_focus": bool(props.get("northern_focus")),
                "centroid": {"longitude": round(centroid[0], 6), "latitude": round(centroid[1], 6)},
                "boundary_source": props.get("source", "unknown"),
                "capabilities": [
                    "local Sentinel-2 NDVI", "live weather and forecast", "vegetation/desert scenario",
                    "land-cover screening", "restoration suitability", "risk intelligence",
                    "field observations", "project registry", "local alerts", "scenario laboratory",
                ],
            })
        return sorted(output, key=lambda item: item["name"])

    async def boundary(self, slug: str) -> dict[str, Any]:
        feature = self.feature(slug)
        return {"type": "FeatureCollection", "features": [feature]}

    async def satellite(self, slug: str, force: bool = False) -> SatelliteData:
        canonical = self.canonical_slug(slug)
        now = datetime.now(timezone.utc)
        cached = self._satellite_cache.get(canonical)
        ttl = max(900, int(self.runtime.settings.satellite_refresh_seconds))
        if cached and not force and (now - cached.fetched_at).total_seconds() < ttl:
            return cached.satellite
        async with self._cache_lock:
            cached = self._satellite_cache.get(canonical)
            if cached and not force and (now - cached.fetched_at).total_seconds() < ttl:
                return cached.satellite
            feature = self.feature(canonical)
            name = str((feature.get("properties") or {}).get("name") or feature_name(feature))
            bbox = self._feature_bounds(feature)
            try:
                data = await self.runtime.sentinel.fetch_bbox_data(bbox, name)
            except Exception as exc:  # noqa: BLE001
                # A live request can fail because of cloud coverage or quota. The
                # fallback remains explicitly labelled demonstration data.
                data = await self._demo_satellite_for_lga(name, bbox, f"LGA satellite request failed ({type(exc).__name__}).")
            self._satellite_cache[canonical] = CachedLGAData(data, now)
            return data

    async def _demo_satellite_for_lga(self, name: str, bbox: tuple[float, float, float, float], reason: str) -> SatelliteData:
        import hashlib
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.runtime.settings.sentinel_lookback_days)
        seed = self.runtime.settings.random_seed + int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:8], 16)
        ndvi, valid = generate_demo_ndvi(72, 72, seed, end)
        version = int(end.timestamp())
        snapshot = SatelliteSnapshot(
            mode="demo",
            fetched_at=end,
            observation_window_start=start,
            observation_window_end=end,
            grid_width=72,
            grid_height=72,
            cloud_limit_percent=self.runtime.settings.sentinel_max_cloud_percent,
            stats=calculate_stats(ndvi, valid),
            source_name=f"Deterministic demonstration surface for {name}",
            note=f"{reason} This LGA-specific raster is demonstration data and not a satellite observation.",
            texture_version=version,
        )
        return SatelliteData(snapshot, ndvi, valid, ndvi_to_texture(ndvi, valid, width=720, height=720))

    async def texture(self, slug: str, layer: str) -> tuple[bytes, int]:
        canonical = self.canonical_slug(slug)
        feature_collection = await self.boundary(canonical)
        feature = feature_collection["features"][0]
        bbox = self._feature_bounds(feature)
        satellite = await self.satellite(canonical)
        version = int(satellite.snapshot.texture_version)
        key = (canonical, layer, version + int(self.runtime.automaton.tick if layer != "ndvi" else 0))
        if key in self._texture_cache:
            return self._texture_cache[key], key[2]
        local = await self._local_arrays(canonical, satellite)
        if layer == "ndvi":
            raw = satellite.texture_png
        elif layer == "simulation":
            raw = simulation_to_texture(local["vegetation"], local["desert"], local["barrier"], 720, 720)
        elif layer == "suitability":
            raw = self._continuous_texture(local["suitability"], "suitability")
        elif layer == "risk":
            raw = self._continuous_texture(local["combined_risk"], "risk")
        elif layer == "landcover":
            raw = self._landcover_texture(local["landcover_labels"], satellite.valid)
        else:
            raise KeyError(layer)
        masked = mask_texture_to_features(raw, feature_collection, bbox)
        self._texture_cache = {item_key: item for item_key, item in self._texture_cache.items() if item_key[0] != canonical or item_key[1] != layer}
        self._texture_cache[key] = masked
        return masked, key[2]

    async def snapshot(self, slug: str) -> dict[str, Any]:
        canonical = self.canonical_slug(slug)
        feature = self.feature(canonical)
        props = feature.get("properties") or {}
        name = str(props.get("name") or feature_name(feature))
        geometry = feature.get("geometry") or {}
        centroid = geometry_centroid(geometry)
        bbox = self._feature_bounds(feature)

        satellite, weather, forecast, rainfall, fire = await asyncio.gather(
            self.satellite(canonical),
            self.runtime.weather_service.fetch(*centroid, name),
            self.runtime.weather_service.fetch_forecast(*centroid, name),
            self.runtime.rainfall_service.fetch(*centroid),
            self.runtime.fires(),
        )
        local = await self._local_arrays(canonical, satellite, weather=weather, rainfall=rainfall, fire=fire)
        hotspots = self._local_hotspots(geometry, centroid, fire.get("hotspots", []))
        projects = self._projects_for_lga(name)
        observations = self._observations_for_lga(name, geometry)
        trees = self._tree_instances(local, geometry, bbox, canonical)
        timeline = await self._timeline(canonical, satellite.snapshot.stats.mean)
        alerts = self._alerts(name, satellite, weather, local, rainfall, hotspots, projects)
        area_km2 = self._geometry_area_km2(geometry)
        local_carbon = self._carbon(area_km2, local, trees)
        interpretations = self._interpretations(
            name=name,
            satellite=satellite,
            weather=weather,
            rainfall=rainfall,
            local=local,
            hotspots=hotspots,
            observations=observations,
            projects=projects,
        )
        settlements = self._settlements(geometry)
        source_mode = self._source_mode([satellite.snapshot.mode, weather.mode, rainfall.get("mode"), fire.get("mode")])

        return {
            "service": "lga-digital-twin",
            "service_version": "5.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "slug": canonical,
            "name": name,
            "route": f"/lga/{canonical}",
            "northern_focus": bool(props.get("northern_focus")),
            "source_mode": source_mode,
            "geography": {
                "centroid": {"longitude": round(centroid[0], 6), "latitude": round(centroid[1], 6)},
                "bbox": [round(value, 6) for value in bbox],
                "area_km2_approx": round(area_km2, 2),
                "boundary_source": props.get("source", "unknown"),
                "settlements": settlements,
            },
            "satellite": satellite.snapshot.model_dump(mode="json"),
            "weather": weather.model_dump(mode="json"),
            "forecast": forecast.model_dump(mode="json"),
            "rainfall_drought": rainfall,
            "vegetation": {
                "mean_ndvi": round(float(satellite.snapshot.stats.mean), 4),
                "valid_fraction": round(float(satellite.snapshot.stats.valid_fraction), 4),
                "bare_fraction": round(float(satellite.snapshot.stats.bare_fraction), 4),
                "sparse_fraction": round(float(satellite.snapshot.stats.sparse_fraction), 4),
                "moderate_fraction": round(float(satellite.snapshot.stats.moderate_fraction), 4),
                "dense_fraction": round(float(satellite.snapshot.stats.dense_fraction), 4),
                "modelled_vegetated_fraction": round(float(np.mean(local["vegetation"] >= 0.38)), 4),
                "tree_instances": len(trees),
            },
            "desertification": {
                "mean_pressure": round(float(np.mean(local["desert"])), 4),
                "high_pressure_fraction": round(float(np.mean(local["desert"] >= 0.60)), 4),
                "bare_exposure_fraction": round(float(np.mean(local["vegetation"] < 0.22)), 4),
                "wind_erosion_risk": round(float(np.mean(local["wind_erosion"])), 4),
                "scenario_tick": int(self.runtime.automaton.tick),
                "mode": "local scenario derived from LGA satellite/weather evidence",
            },
            "restoration": {
                "mean_suitability": round(float(np.mean(local["suitability"])), 4),
                "high_suitability_fraction": round(float(np.mean(local["suitability"] >= 0.72)), 4),
                "conditional_fraction": round(float(np.mean((local["suitability"] >= 0.48) & (local["suitability"] < 0.72))), 4),
                "barrier_fraction": round(float(np.mean(local["barrier"] >= 0.08)), 4),
                "projects": len(projects),
                "field_observations": len(observations),
            },
            "landcover": local["landcover"],
            "risk": {
                "combined_mean": round(float(np.mean(local["combined_risk"])), 4),
                "runoff_mean": round(float(np.mean(local["runoff"])), 4),
                "infiltration_mean": round(float(np.mean(local["infiltration"])), 4),
                "fire_exposure_mean": round(float(np.mean(local["fire_exposure"])), 4),
            },
            "thermal_anomalies": {
                "mode": fire.get("mode", "unavailable"),
                "within_lga": [item for item in hotspots if item["relation"] == "inside"],
                "nearby": hotspots,
                "count": len(hotspots),
                "note": "FIRMS points are satellite thermal anomalies and do not establish cause or damage severity.",
            },
            "carbon_ecosystems": local_carbon,
            "timeline": timeline,
            "trees": trees,
            "projects": projects,
            "field_observations": observations,
            "alerts": alerts,
            "interpretations": interpretations,
            "provenance": [
                {"kind": "observation", "source": satellite.snapshot.source_name, "mode": satellite.snapshot.mode},
                {"kind": "observation", "source": "OpenWeather current and forecast", "mode": weather.mode},
                {"kind": "context", "source": rainfall.get("source", "Open-Meteo"), "mode": rainfall.get("mode", "unavailable")},
                {"kind": "context", "source": fire.get("source", "NASA FIRMS"), "mode": fire.get("mode", "unavailable")},
                {"kind": "simulation", "source": "LGA-scoped transparent vegetation/desert/restoration screening model", "mode": "derived"},
            ],
            "limitations": [
                "Satellite pixels and weather API values are not field surveys.",
                "The local cellular state is a transparent scenario derived from available evidence, not measured land degradation.",
                "Carbon, erosion, hydrology and suitability values are screening estimates and require local validation.",
                "Thermal anomalies do not prove wildfire, burning cause or ecological damage.",
            ],
        }

    async def scenario(self, slug: str, parameters: dict[str, float]) -> dict[str, Any]:
        snapshot = await self.snapshot(slug)
        vegetation = float(snapshot["vegetation"]["modelled_vegetated_fraction"])
        desert = float(snapshot["desertification"]["high_pressure_fraction"])
        barrier = float(snapshot["restoration"]["barrier_fraction"])
        aridity = float(np.clip(parameters.get("aridity_pressure", 0.58), 0, 1))
        grazing = float(np.clip(parameters.get("grazing_pressure", 0.35), 0, 1))
        rainfall = float(np.clip(parameters.get("rainfall_support", 0.35), 0, 1))
        restoration = float(np.clip(parameters.get("restoration_effort", 0.45), 0, 1))
        maintenance = float(np.clip(parameters.get("barrier_maintenance", 0.70), 0, 1))
        steps = int(np.clip(parameters.get("steps", 36), 6, 120))
        series = []
        for step in range(steps + 1):
            if step:
                desert += 0.014 * (aridity + grazing * 0.65) * (1 - vegetation) - 0.011 * (rainfall + restoration * barrier) * desert
                vegetation += 0.015 * (rainfall + restoration) * (1 - desert) * (1 - vegetation) - 0.010 * (aridity + grazing) * desert * vegetation
                barrier += 0.018 * restoration * maintenance * max(0.025, 1 - barrier) - 0.011 * (1 - maintenance) * desert * barrier
                vegetation, desert, barrier = (float(np.clip(value, 0, 1)) for value in (vegetation, desert, barrier))
            series.append({"step": step, "vegetation": round(vegetation, 4), "desert": round(desert, 4), "barrier": round(barrier, 4)})
        return {
            "slug": snapshot["slug"],
            "name": snapshot["name"],
            "mode": "local scenario experiment",
            "parameters": {"aridity_pressure": aridity, "grazing_pressure": grazing, "rainfall_support": rainfall, "restoration_effort": restoration, "barrier_maintenance": maintenance, "steps": steps},
            "series": series,
            "outcome": {
                "vegetation_change": round(series[-1]["vegetation"] - series[0]["vegetation"], 4),
                "desert_change": round(series[-1]["desert"] - series[0]["desert"], 4),
                "barrier_change": round(series[-1]["barrier"] - series[0]["barrier"], 4),
            },
            "limitations": "This LGA trajectory is a scenario experiment, not an operational forecast.",
        }

    async def _local_arrays(
        self,
        slug: str,
        satellite: SatelliteData,
        weather: Any | None = None,
        rainfall: dict[str, Any] | None = None,
        fire: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        feature = self.feature(slug)
        geometry = feature.get("geometry") or {}
        weather = weather or await self.runtime.weather_service.fetch(*geometry_centroid(geometry), feature_name(feature))
        rainfall = rainfall or await self.runtime.rainfall_service.fetch(*geometry_centroid(geometry))
        fire = fire or await self.runtime.fires()
        ndvi = np.nan_to_num(satellite.ndvi.astype(np.float32), nan=-0.1)
        valid = satellite.valid.astype(bool)
        ndvi = np.where(valid, ndvi, np.nanmedian(ndvi[valid]) if np.any(valid) else 0.1)
        vegetation = np.clip((ndvi + 0.08) / 0.78, 0, 1)
        humidity = float(np.clip(weather.humidity_percent / 100.0, 0, 1))
        rain90 = float(np.clip(float((rainfall.get("totals_mm") or {}).get("90", 0.0)) / 360.0, 0, 1))
        temperature_stress = float(np.clip((weather.temperature_c - 29.0) / 15.0, 0, 1))
        scenario = self.runtime.automaton.parameters
        moisture = np.clip(0.38 * vegetation + 0.30 * humidity + 0.22 * rain90 + 0.10 * scenario.rainfall_support - 0.15 * temperature_stress, 0, 1)
        desert = np.clip(
            0.52 - ndvi * 0.62 + scenario.aridity_pressure * 0.22 + scenario.grazing_pressure * 0.15
            - moisture * 0.27 - scenario.restoration_effort * 0.08,
            0,
            1,
        )
        barrier = np.zeros_like(vegetation, dtype=np.float32)
        global_values = self.runtime._simulation_inside_geometry(geometry)
        if global_values[0].size:
            mean_barrier = float(np.mean(global_values[2]))
            # Preserve committed northern barriers as a visible local influence.
            barrier += np.clip(mean_barrier * (0.55 + vegetation * 0.75), 0, 1)
        projects = self._projects_for_lga(feature_name(feature))
        if projects:
            barrier = np.clip(barrier + min(0.30, len(projects) * 0.035), 0, 1)

        gy, gx = np.gradient(0.58 * desert - 0.28 * vegetation)
        slope = self._normalise(np.hypot(gx, gy))
        hotspot = self._hotspot_grid(vegetation.shape, self._feature_bounds(feature), fire.get("hotspots", []))
        wind = float(np.clip(weather.wind_speed_mps / 12.0, 0, 1))
        wind_erosion = np.clip((1 - vegetation) * desert * (0.35 + wind) * (1 - barrier * 0.72), 0, 1)
        current_rain = float(np.clip(weather.rain_1h_mm / 10.0, 0, 1))
        runoff = np.clip((0.20 + current_rain + rain90 * 0.25) * slope * (1 - vegetation * 0.55) * (1 - moisture * 0.35), 0, 1)
        infiltration = np.clip(vegetation * 0.55 + moisture * 0.38 + barrier * 0.18 - slope * 0.12, 0, 1)
        combined_risk = np.clip(0.40 * wind_erosion + 0.26 * runoff + 0.20 * hotspot + 0.14 * (1 - infiltration), 0, 1)
        suitability = np.clip(
            0.31 * (desert * (0.45 + moisture) * (1 - vegetation * 0.45))
            + 0.24 * moisture + 0.14 * (1 - slope) + 0.11 * rain90 + 0.10 * (1 - hotspot)
            + 0.10 * (1 - barrier),
            0,
            1,
        )
        labels, landcover = self._landcover(ndvi, vegetation, moisture, desert, valid)
        return {
            "vegetation": vegetation.astype(np.float32),
            "desert": desert.astype(np.float32),
            "barrier": barrier.astype(np.float32),
            "moisture": moisture.astype(np.float32),
            "suitability": suitability.astype(np.float32),
            "wind_erosion": wind_erosion.astype(np.float32),
            "runoff": runoff.astype(np.float32),
            "infiltration": infiltration.astype(np.float32),
            "fire_exposure": hotspot.astype(np.float32),
            "combined_risk": combined_risk.astype(np.float32),
            "landcover_labels": labels,
            "landcover": landcover,
        }

    async def _timeline(self, slug: str, local_ndvi: float) -> dict[str, Any]:
        global_story = await self.runtime.temporal()
        points = list(global_story.get("points") or [])[-36:]
        if not points:
            return {"mode": "unavailable", "points": [], "note": "No timeline is available."}
        current_global = float(points[-1].get("ndvi") or local_ndvi)
        delta = local_ndvi - current_global
        local_points = []
        for item in points:
            ndvi = float(np.clip(float(item.get("ndvi") or 0.0) + delta, -0.1, 0.9))
            local_points.append({
                "period": item.get("period"),
                "ndvi": round(ndvi, 4),
                "vegetated_fraction": round(float(np.clip((ndvi + 0.05) / 0.72, 0, 1)), 4),
                "desert_fraction": round(float(np.clip(0.66 - ndvi, 0, 1)), 4),
                "rain_mm": item.get("rain_mm"),
                "mode": "lga-localised-" + str(item.get("mode") or global_story.get("mode") or "derived"),
            })
        return {
            "mode": "lga_localised_" + str(global_story.get("mode") or "derived"),
            "points": local_points,
            "trend": "greening" if local_points[-1]["ndvi"] - local_points[max(0, len(local_points) - 13)]["ndvi"] > 0.03 else "browning" if local_points[-1]["ndvi"] - local_points[max(0, len(local_points) - 13)]["ndvi"] < -0.03 else "stable_or_seasonal",
            "note": "Historical shape follows the platform timeline and is offset to the current LGA NDVI. Points are labelled localised rather than direct LGA satellite observations unless an archive is explicitly available.",
        }

    def _projects_for_lga(self, name: str) -> list[dict[str, Any]]:
        target = slugify(name)
        return [item for item in self.runtime.store.list_projects() if slugify(str(item.get("lga") or "")) == target]

    def _observations_for_lga(self, name: str, geometry: dict[str, Any]) -> list[dict[str, Any]]:
        target = slugify(name)
        output = []
        for item in self.runtime.store.list_observations(1000):
            matches_name = slugify(str(item.get("lga") or "")) == target
            matches_geometry = point_in_geometry(float(item.get("longitude") or 0), float(item.get("latitude") or 0), geometry)
            if matches_name or matches_geometry:
                output.append(item)
        return output

    def _settlements(self, geometry: dict[str, Any]) -> list[dict[str, Any]]:
        output = []
        for feature in self.runtime.locations.get("features", []):
            coordinates = (feature.get("geometry") or {}).get("coordinates") or []
            if len(coordinates) >= 2 and point_in_geometry(float(coordinates[0]), float(coordinates[1]), geometry):
                props = feature.get("properties") or {}
                output.append({"name": props.get("name", "Mapped location"), "longitude": coordinates[0], "latitude": coordinates[1]})
        return output

    def _tree_instances(self, local: dict[str, Any], geometry: dict[str, Any], bbox: tuple[float, float, float, float], slug: str) -> list[dict[str, Any]]:
        vegetation = local["vegetation"]
        barrier = local["barrier"]
        desert = local["desert"]
        height, width = vegetation.shape
        west, south, east, north = bbox
        candidates = np.argwhere((vegetation > 0.43) | (barrier > 0.08))
        if not candidates.size:
            return []
        step = max(1, int(math.ceil(len(candidates) / 620)))
        output = []
        for index, (row, col) in enumerate(candidates[::step][:620]):
            lon = west + (float(col) + 0.5) / width * (east - west)
            lat = north - (float(row) + 0.5) / height * (north - south)
            if not point_in_geometry(lon, lat, geometry):
                continue
            health = float(np.clip(vegetation[row, col] * (1 - desert[row, col] * 0.55), 0.08, 1))
            is_barrier = bool(barrier[row, col] > 0.08)
            output.append({
                "id": index,
                "longitude": round(lon, 6),
                "latitude": round(lat, 6),
                "health": round(health, 4),
                "height_m": round(1.2 + health * (5.8 if is_barrier else 4.8), 2),
                "crown_m": round(0.6 + health * (2.8 if is_barrier else 2.25), 2),
                "barrier": is_barrier,
                "species_form": "shelterbelt" if is_barrier else "savanna" if health > 0.42 else "shrub",
            })
        return output

    def _local_hotspots(self, geometry: dict[str, Any], centroid: tuple[float, float], hotspots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output = []
        for item in hotspots:
            lon = float(item.get("longitude") or 0.0)
            lat = float(item.get("latitude") or 0.0)
            inside = point_in_geometry(lon, lat, geometry)
            distance = haversine_km(centroid, (lon, lat))
            if inside or distance <= 45:
                enriched = dict(item)
                enriched["distance_from_centroid_km"] = round(distance, 2)
                enriched["relation"] = "inside" if inside else "nearby"
                output.append(enriched)
        return sorted(output, key=lambda item: item["distance_from_centroid_km"])

    def _alerts(self, name: str, satellite: SatelliteData, weather: Any, local: dict[str, Any], rainfall: dict[str, Any], hotspots: list[dict[str, Any]], projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        def add(kind: str, severity: str, title: str, body: str) -> None:
            items.append({"kind": kind, "severity": severity, "title": title, "body": body, "generated_at": datetime.now(timezone.utc).isoformat()})
        drought_score = float((rainfall.get("drought_screen") or {}).get("score") or 0)
        if drought_score >= 65:
            add("drought", "high", f"Moisture deficit in {name}", f"The rainfall screening score is {drought_score:.0f}/100.")
        if satellite.snapshot.stats.mean < 0.18:
            add("vegetation", "high", "Low observed greenness", f"The current LGA NDVI mean is {satellite.snapshot.stats.mean:.2f}.")
        if float(np.mean(local["desert"] >= 0.60)) > 0.38:
            add("desertification", "medium", "Elevated scenario pressure", "A substantial fraction of LGA scenario cells are in the high-pressure class.")
        if weather.wind_speed_mps >= 8 and float(np.mean(local["wind_erosion"])) >= 0.35:
            add("erosion", "medium", "Wind-erosion watch", f"Wind is {weather.wind_speed_mps:.1f} m/s while exposed model cells are present.")
        if hotspots:
            add("thermal", "high", "Thermal anomaly context", f"{len(hotspots)} FIRMS detection(s) are inside or within 45 km of the LGA centroid.")
        for project in projects:
            inspections = project.get("inspections") or []
            if inspections and float(inspections[0].get("survival_percent") or 100) < 55:
                add("project", "high", f"Low survival: {project.get('name')}", f"Latest recorded survival is {inspections[0].get('survival_percent')}%.")
        if not items:
            add("status", "low", "No high-priority local alert", "Current local screening thresholds did not trigger a high-priority alert.")
        return items

    def _interpretations(self, *, name: str, satellite: SatelliteData, weather: Any, rainfall: dict[str, Any], local: dict[str, Any], hotspots: list[dict[str, Any]], observations: list[dict[str, Any]], projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ndvi = satellite.snapshot.stats.mean
        cover = "stronger" if ndvi >= 0.50 else "moderate" if ndvi >= 0.30 else "sparse" if ndvi >= 0.15 else "very limited"
        pressure = float(np.mean(local["desert"]))
        wind_transport = (weather.wind_direction_deg + 180) % 360
        return [
            {"kind": "observation", "title": "Current vegetation evidence", "body": f"The LGA-scoped Sentinel-2 NDVI mean is {ndvi:.2f}, indicating {cover} spectral greenness in the current valid-pixel mosaic.", "confidence": "high" if satellite.snapshot.stats.valid_fraction >= 0.7 else "medium", "evidence": [f"Valid pixel coverage: {satellite.snapshot.stats.valid_fraction * 100:.1f}%", satellite.snapshot.source_name]},
            {"kind": "weather", "title": "Current atmospheric forcing", "body": f"{weather.condition} conditions are reported at {weather.temperature_c:.1f}°C, {weather.humidity_percent:.0f}% humidity and {weather.wind_speed_mps:.1f} m/s wind from {weather.wind_direction_cardinal}. Material transported with the wind would generally move toward approximately {wind_transport:.0f}°.", "confidence": "high" if weather.mode == "live" else "low", "evidence": [f"Weather mode: {weather.mode}", f"Rain in last hour: {weather.rain_1h_mm:.1f} mm"]},
            {"kind": "simulation", "title": "Local desertification scenario", "body": f"The transparent LGA model has a mean desert-pressure score of {pressure:.2f}. It combines the current NDVI mosaic with weather, rainfall and the platform scenario settings; it is not a measured desertification rate.", "confidence": "not-applicable", "evidence": ["Cellular screening model", "Current scenario parameters"]},
            {"kind": "interpretation", "title": "Restoration opportunity", "body": f"Mean screening suitability is {float(np.mean(local['suitability'])):.2f}. Higher values identify degraded-but-recoverable cells with better moisture, lower terrain-gradient and lower thermal-anomaly penalties.", "confidence": "medium", "evidence": ["NDVI", "modelled moisture", "rainfall context", "FIRMS proximity"]},
            {"kind": "external", "title": "Local verification coverage", "body": f"The registry currently contains {len(observations)} field observation(s) and {len(projects)} restoration project(s) linked to {name}. These records provide the strongest route for checking satellite and model interpretations.", "confidence": "high", "evidence": ["Platform field registry", "Restoration project registry"]},
            {"kind": "limitation", "title": "What the twin cannot prove", "body": (f"{len(hotspots)} nearby thermal anomaly record(s) are shown, but FIRMS does not establish cause. " if hotspots else "No nearby FIRMS anomaly is currently returned, which does not prove that no fire exists. ") + "NDVI, rainfall and scenario outputs must be combined with field knowledge before land-management decisions.", "confidence": "not-applicable", "evidence": []},
        ]

    def _carbon(self, area_km2: float, local: dict[str, Any], trees: list[dict[str, Any]]) -> dict[str, Any]:
        mean_veg = float(np.mean(local["vegetation"]))
        dense = float(np.mean(local["vegetation"] >= 0.62))
        agbd = 5.0 + 33.0 * mean_veg + 18.0 * dense
        uncertainty = max(8.0, agbd * 0.45)
        hectares = area_km2 * 100
        carbon_t = agbd * hectares * 0.47
        services = {
            "wind_erosion_protection": round(float(np.clip(mean_veg * 70 + np.mean(local["barrier"]) * 65, 0, 100)), 1),
            "water_infiltration_support": round(float(np.clip(np.mean(local["infiltration"]) * 100, 0, 100)), 1),
            "habitat_connectivity": round(float(np.clip(dense * 85 + np.mean(local["barrier"]) * 45, 0, 100)), 1),
            "soil_retention": round(float(np.clip(mean_veg * 65 + np.mean(local["barrier"]) * 55, 0, 100)), 1),
        }
        return {
            "mode": "LGA modelled screening",
            "aboveground_biomass_density_mg_ha": round(agbd, 2),
            "uncertainty_mg_ha": round(uncertainty, 2),
            "estimated_total_carbon_t": round(carbon_t, 0),
            "procedural_tree_count": len(trees),
            "ecosystem_service_scores": services,
            "limitations": "The result is not a certified biomass inventory or carbon-credit account.",
        }

    @staticmethod
    def _landcover(ndvi: np.ndarray, vegetation: np.ndarray, moisture: np.ndarray, desert: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
        # 0 water, 1 trees, 2 grass, 3 crops, 4 shrub, 5 built, 6 bare
        scores = np.zeros((*ndvi.shape, 7), dtype=np.float32)
        scores[..., 0] = np.clip((0.03 - ndvi) * 4 + moisture * 0.12, 0, 1)
        scores[..., 1] = np.clip((ndvi - 0.42) * 2.4 + vegetation * 0.35, 0, 1)
        scores[..., 2] = np.clip(1 - np.abs(ndvi - 0.35) * 3.0, 0, 1) * (0.5 + moisture * 0.5)
        scores[..., 3] = np.clip(1 - np.abs(ndvi - 0.52) * 3.5, 0, 1) * 0.58
        scores[..., 4] = np.clip(1 - np.abs(ndvi - 0.23) * 4.2, 0, 1) * 0.72
        pattern = (np.sin(np.indices(ndvi.shape)[1] * 0.43) + np.cos(np.indices(ndvi.shape)[0] * 0.37) > 1.84)
        scores[..., 5] = pattern.astype(np.float32) * 0.25
        scores[..., 6] = np.clip(desert * 0.8 + (0.17 - ndvi) * 2.2, 0, 1)
        scores *= valid[..., None]
        labels = np.argmax(scores, axis=2)
        names = ["water", "trees", "grass", "crops", "shrub_scrub", "built", "bare"]
        classes = {name: round(float(np.mean(labels[valid] == index)), 4) if np.any(valid) else 0 for index, name in enumerate(names)}
        return labels, {
            "mode": "LGA derived screening",
            "dominant_class": max(classes, key=classes.get),
            "classes": classes,
            "limitations": "Land-cover classes are a transparent screening interpretation, not an externally validated classification.",
        }

    @staticmethod
    def _landcover_texture(labels: np.ndarray, valid: np.ndarray) -> bytes:
        palette = np.asarray([[55, 130, 240], [28, 118, 52], [92, 178, 76], [222, 190, 70], [145, 140, 66], [194, 75, 70], [195, 145, 75]], dtype=np.uint8)
        rgba = np.zeros((*labels.shape, 4), dtype=np.uint8)
        rgba[..., :3] = palette[labels]
        rgba[..., 3] = np.where(valid, 205, 0).astype(np.uint8)
        return LGATwinService._png(rgba)

    @staticmethod
    def _continuous_texture(values: np.ndarray, palette: str) -> bytes:
        value = np.clip(values, 0, 1)
        rgba = np.zeros((*value.shape, 4), dtype=np.uint8)
        if palette == "suitability":
            rgba[..., 0] = np.clip(210 - value * 180, 0, 255)
            rgba[..., 1] = np.clip(70 + value * 170, 0, 255)
            rgba[..., 2] = np.clip(55 + value * 50, 0, 255)
        else:
            rgba[..., 0] = np.clip(45 + value * 210, 0, 255)
            rgba[..., 1] = np.clip(170 - value * 145, 0, 255)
            rgba[..., 2] = np.clip(90 - value * 55, 0, 255)
        rgba[..., 3] = np.clip(45 + value * 185, 0, 225).astype(np.uint8)
        return LGATwinService._png(rgba)

    @staticmethod
    def _png(rgba: np.ndarray) -> bytes:
        output = BytesIO()
        Image.fromarray(rgba.astype(np.uint8), "RGBA").resize((720, 720), Image.Resampling.BILINEAR).save(output, format="PNG", optimize=True)
        return output.getvalue()

    @staticmethod
    def _normalise(values: np.ndarray) -> np.ndarray:
        minimum = float(np.nanmin(values))
        maximum = float(np.nanmax(values))
        return (values - minimum) / max(maximum - minimum, 1e-6)

    @staticmethod
    def _hotspot_grid(shape: tuple[int, int], bbox: tuple[float, float, float, float], hotspots: list[dict[str, Any]]) -> np.ndarray:
        height, width = shape
        west, south, east, north = bbox
        yy, xx = np.mgrid[0:height, 0:width]
        output = np.zeros(shape, dtype=np.float32)
        for item in hotspots:
            lon = float(item.get("longitude") or 0.0)
            lat = float(item.get("latitude") or 0.0)
            x = (lon - west) / max(east - west, 1e-9) * (width - 1)
            y = (north - lat) / max(north - south, 1e-9) * (height - 1)
            frp = float(item.get("frp_mw") or 1.0)
            output = np.maximum(output, np.exp(-np.hypot(xx - x, yy - y) / max(2.5, min(width, height) * 0.09)) * np.clip(frp / 20.0, 0.2, 1.0))
        return np.clip(output, 0, 1)

    @staticmethod
    def _feature_bounds(feature: dict[str, Any]) -> tuple[float, float, float, float]:
        return collection_bounds({"type": "FeatureCollection", "features": [feature]})

    @staticmethod
    def _geometry_area_km2(geometry: dict[str, Any]) -> float:
        total = 0.0
        radius = 6371.0088
        for polygon in iter_polygons(geometry):
            for ring_index, ring in enumerate(polygon):
                if len(ring) < 3:
                    continue
                mean_lat = math.radians(sum(float(point[1]) for point in ring) / len(ring))
                projected = [(radius * math.radians(float(point[0])) * math.cos(mean_lat), radius * math.radians(float(point[1]))) for point in ring]
                area = abs(sum(projected[i][0] * projected[(i + 1) % len(projected)][1] - projected[(i + 1) % len(projected)][0] * projected[i][1] for i in range(len(projected))) / 2)
                total += area if ring_index == 0 else -area
        return max(0.0, total)

    @staticmethod
    def _source_mode(modes: list[Any]) -> str:
        values = {str(value or "unavailable") for value in modes}
        if values == {"live"}:
            return "live"
        if "live" in values:
            return "mixed"
        if "demo" in values:
            return "demo"
        return "unavailable"
