from __future__ import annotations

import heapq
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from app.config import Settings
from app.services.geometry import geometry_centroid
from app.services.texture import array_to_rgba_png

LAND_CLASSES = [
    "water",
    "trees",
    "grass",
    "flooded_vegetation",
    "crops",
    "shrub_scrub",
    "built",
    "bare",
    "snow_ice",
]


class IntelligenceEngine:
    """Transparent analytical layer built from available observations and model state.

    Outputs explicitly report whether they are observed, externally supplied,
    derived or scenario-modelled. The engine is intentionally lightweight so it
    can run on a small public Render instance.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._landcover_texture: bytes | None = None
        self._suitability_texture: bytes | None = None
        self._risk_texture: bytes | None = None
        self._versions = {"landcover": 0, "suitability": 0, "risk": 0}

    def temporal_story(
        self,
        history: list[dict[str, Any]],
        rainfall: dict[str, Any],
        current_ndvi: float,
        source_mode: str,
    ) -> dict[str, Any]:
        points = self._history_to_monthly(history)
        if len(points) < 12:
            points = self._derived_monthly_story(rainfall, current_ndvi)
            mode = "derived"
            note = (
                "The long timeline is a deterministic seasonal reconstruction anchored to the current NDVI and rainfall series. "
                "It is not a historical satellite archive. Use the protected Sentinel backfill action to populate observed mosaics."
            )
        else:
            mode = "recorded"
            note = "Timeline points are aggregated from observations and simulation frames recorded by this deployment."
        for point in points:
            point["vegetation_change"] = round(point["ndvi"] - points[0]["ndvi"], 4)
        latest = points[-1] if points else {"ndvi": current_ndvi}
        previous_year = points[-13] if len(points) >= 13 else points[0] if points else latest
        change = float(latest["ndvi"] - previous_year["ndvi"])
        return {
            "mode": mode,
            "source_mode": source_mode,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "points": points,
            "year_on_year_ndvi_change": round(change, 4),
            "trend": "greening" if change > 0.03 else "browning" if change < -0.03 else "stable_or_seasonal",
            "note": note,
            "limitations": "NDVI seasonality, crop cycles, clouds, soil brightness and sensor timing can produce change without permanent land degradation or restoration.",
        }

    @staticmethod
    def _history_to_monthly(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for record in history:
            stamp = str(record.get("timestamp") or "")
            if len(stamp) < 7:
                continue
            groups.setdefault(stamp[:7], []).append(record)
        output = []
        for period, records in sorted(groups.items()):
            output.append({
                "period": period,
                "ndvi": round(float(np.mean([float(item.get("ndvi_mean") or 0.0) for item in records])), 4),
                "vegetated_fraction": round(float(np.mean([float(item.get("vegetated_fraction") or 0.0) for item in records])), 4),
                "desert_fraction": round(float(np.mean([float(item.get("desert_fraction") or 0.0) for item in records])), 4),
                "rain_mm": round(float(np.sum([float(item.get("rain_1h_mm") or 0.0) for item in records])), 2),
                "mode": "recorded",
            })
        return output

    def _derived_monthly_story(self, rainfall: dict[str, Any], current_ndvi: float) -> list[dict[str, Any]]:
        monthly_rain = {item["period"]: float(item["rain_mm"]) for item in rainfall.get("monthly", [])}
        end = datetime.now(timezone.utc).replace(day=1)
        rng = np.random.default_rng(self.settings.random_seed + 404)
        output: list[dict[str, Any]] = []
        for offset in range(35, -1, -1):
            year = end.year
            month = end.month - offset
            while month <= 0:
                month += 12
                year -= 1
            period = f"{year:04d}-{month:02d}"
            seasonal = 0.12 * math.sin((month - 4) / 12 * math.tau)
            rainfall_term = min(0.15, monthly_rain.get(period, 55.0) / 900.0)
            trend = (35 - offset) * 0.0007
            ndvi = float(np.clip(current_ndvi + seasonal + rainfall_term + trend + rng.normal(0, 0.012), -0.05, 0.78))
            output.append({
                "period": period,
                "ndvi": round(ndvi, 4),
                "vegetated_fraction": round(float(np.clip((ndvi + 0.05) / 0.7, 0.0, 1.0)), 4),
                "desert_fraction": round(float(np.clip(0.72 - ndvi, 0.0, 1.0)), 4),
                "rain_mm": round(monthly_rain.get(period, 55.0 + seasonal * 260.0), 2),
                "mode": "derived",
            })
        return output

    def land_cover(
        self,
        ndvi: np.ndarray,
        valid: np.ndarray,
        radar_rvi: np.ndarray | None,
        simulation: Any,
        external: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        height, width = ndvi.shape
        rvi = self._resize(radar_rvi, height, width) if radar_rvi is not None else np.clip((ndvi + 0.1) / 0.8, 0.0, 1.0)
        veg = self._resize(simulation.vegetation, height, width)
        desert = self._resize(simulation.desert, height, width)
        moisture = self._resize(simulation.moisture, height, width)

        probabilities = np.zeros((height, width, len(LAND_CLASSES)), dtype=np.float32)
        probabilities[..., 0] = np.clip((0.02 - ndvi) * 5.0 + moisture * 0.10, 0, 1)  # water proxy
        probabilities[..., 1] = np.clip((ndvi - 0.42) * 2.6 + rvi * 0.55, 0, 1)
        probabilities[..., 2] = np.clip(1.0 - np.abs(ndvi - 0.38) * 3.1, 0, 1) * (0.45 + moisture * 0.55)
        probabilities[..., 3] = np.clip(moisture * 1.5 + ndvi * 0.3 - 0.65, 0, 1)
        probabilities[..., 4] = np.clip(1.0 - np.abs(ndvi - 0.52) * 3.5, 0, 1) * 0.62
        probabilities[..., 5] = np.clip(1.0 - np.abs(ndvi - 0.24) * 4.0, 0, 1) * (0.55 + rvi * 0.35)
        built_pattern = (np.sin(np.indices((height, width))[1] * 0.38) + np.cos(np.indices((height, width))[0] * 0.41) > 1.78)
        probabilities[..., 6] = built_pattern.astype(np.float32) * 0.35
        probabilities[..., 7] = np.clip(desert * 0.75 + (0.18 - ndvi) * 2.2, 0, 1)
        probabilities[..., 8] = 0.0
        probabilities *= valid[..., None]
        denominator = np.sum(probabilities, axis=2, keepdims=True)
        probabilities = probabilities / np.maximum(denominator, 1e-6)
        labels = np.argmax(probabilities, axis=2)
        confidence = np.max(probabilities, axis=2)

        counts = {name: round(float(np.mean(labels[valid] == index)), 4) if np.any(valid) else 0.0 for index, name in enumerate(LAND_CLASSES)}
        dominant = max(counts, key=counts.get)
        mean_conf = float(np.mean(confidence[valid])) if np.any(valid) else 0.0
        mode = "external" if external else "derived"
        note = (
            "External Dynamic World statistics were supplied."
            if external
            else "Land-cover probabilities are a transparent platform-derived classification from NDVI, radar signal and scenario state; they are not Dynamic World observations."
        )
        if external and isinstance(external.get("classes"), dict):
            counts = {key: float(value) for key, value in external["classes"].items() if key in LAND_CLASSES}
            dominant = max(counts, key=counts.get) if counts else dominant
        self._versions["landcover"] += 1
        self._landcover_texture = self._landcover_texture_png(labels, confidence, valid)
        return {
            "mode": mode,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "classes": counts,
            "dominant_class": dominant,
            "mean_confidence": round(mean_conf, 4),
            "texture_version": self._versions["landcover"],
            "attribution": "Dynamic World by Google/WRI/NGS" if external else "Platform-derived screening classification",
            "note": note,
            "limitations": "The derived layer should not be used as a replacement for an externally validated land-cover product or field survey.",
        }

    @staticmethod
    def _landcover_texture_png(labels: np.ndarray, confidence: np.ndarray, valid: np.ndarray) -> bytes:
        palette = np.asarray([
            [65, 130, 255], [20, 110, 45], [92, 175, 70], [70, 190, 165], [224, 190, 65],
            [154, 145, 65], [205, 70, 70], [197, 151, 82], [220, 240, 250],
        ], dtype=np.uint8)
        rgba = np.zeros((*labels.shape, 4), dtype=np.uint8)
        rgba[..., :3] = palette[labels]
        rgba[..., 3] = np.where(valid, np.clip(90 + confidence * 150, 0, 235), 0).astype(np.uint8)
        return array_to_rgba_png(rgba)

    def suitability(
        self,
        state: Any,
        locations: dict[str, Any],
        bbox: tuple[float, float, float, float],
        rainfall: dict[str, Any],
        fire: dict[str, Any],
    ) -> dict[str, Any]:
        veg = state.vegetation.astype(np.float32)
        desert = state.desert.astype(np.float32)
        moisture = state.moisture.astype(np.float32)
        barrier = state.barrier.astype(np.float32)
        slope_proxy = self._normalise(np.hypot(*np.gradient(0.55 * desert - 0.35 * veg)))
        settlement_access = self._settlement_access(veg.shape, locations, bbox)
        rainfall_support = float(np.clip(float(rainfall.get("totals_mm", {}).get("90", 0.0)) / 320.0, 0.0, 1.0))
        hotspot_penalty = self._hotspot_penalty(veg.shape, fire.get("hotspots", []), bbox)
        degraded_but_recoverable = np.clip(desert * (0.45 + moisture) * (1.0 - veg * 0.45), 0, 1)
        score = (
            0.30 * degraded_but_recoverable
            + 0.22 * moisture
            + 0.16 * settlement_access
            + 0.12 * (1.0 - slope_proxy)
            + 0.10 * rainfall_support
            + 0.10 * (1.0 - hotspot_penalty)
        )
        score *= (1.0 - barrier * 0.45)
        score = np.clip(score, 0.0, 1.0)
        classes = {
            "high": round(float(np.mean(score >= 0.72)), 4),
            "conditional": round(float(np.mean((score >= 0.48) & (score < 0.72))), 4),
            "low": round(float(np.mean((score >= 0.28) & (score < 0.48))), 4),
            "unsuitable_pending_verification": round(float(np.mean(score < 0.28)), 4),
        }
        self._versions["suitability"] += 1
        self._suitability_texture = self._continuous_texture(score, "suitability")
        return {
            "mode": "screening_model",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mean_score": round(float(np.mean(score)), 4),
            "classes": classes,
            "texture_version": self._versions["suitability"],
            "grid": score.round(4).tolist(),
            "factors": [
                {"name": "degraded but recoverable condition", "weight": 0.30},
                {"name": "modelled moisture support", "weight": 0.22},
                {"name": "settlement/access proximity", "weight": 0.16},
                {"name": "terrain-gradient proxy", "weight": 0.12},
                {"name": "90-day rainfall support", "weight": 0.10},
                {"name": "thermal-anomaly avoidance", "weight": 0.10},
            ],
            "limitations": (
                "This is a screening suitability model. It does not determine land tenure, community consent, soil chemistry, groundwater, species choice, cost or legal feasibility."
            ),
        }

    def optimise_routes(
        self,
        score_grid: np.ndarray,
        bbox: tuple[float, float, float, float],
        start: tuple[float, float] | None = None,
        end: tuple[float, float] | None = None,
    ) -> dict[str, Any]:
        height, width = score_grid.shape
        start_cell = self._coordinate_to_cell(start, bbox, width, height) if start else (max(1, int(width * 0.08)), int(height * 0.55))
        end_cell = self._coordinate_to_cell(end, bbox, width, height) if end else (min(width - 2, int(width * 0.92)), int(height * 0.38))
        variants = [
            ("maximum_restoration_benefit", 1.0, 0.08),
            ("lowest_maintenance_burden", 0.65, 0.25),
            ("balanced_protection_route", 0.82, 0.16),
        ]
        routes = []
        for name, suitability_weight, length_weight in variants:
            path = self._a_star(score_grid, start_cell, end_cell, suitability_weight, length_weight)
            coordinates = [self._cell_to_coordinate(cell, bbox, width, height) for cell in path]
            scores = [float(score_grid[cell[1], cell[0]]) for cell in path]
            length_km = sum(self._haversine(a, b) for a, b in zip(coordinates[:-1], coordinates[1:]))
            routes.append({
                "id": name,
                "name": name.replace("_", " ").title(),
                "coordinates": coordinates,
                "length_km": round(length_km, 2),
                "mean_suitability": round(float(np.mean(scores)) if scores else 0.0, 4),
                "estimated_cells": len(path),
                "screening_note": "Optimised against the displayed model factors; field validation is required.",
            })
        return {
            "mode": "scenario_optimisation",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "routes": routes,
            "start": routes[0]["coordinates"][0] if routes and routes[0]["coordinates"] else None,
            "end": routes[0]["coordinates"][-1] if routes and routes[0]["coordinates"] else None,
            "limitations": "The routes do not establish land availability, tenure, planting permissions, water access or implementation cost.",
        }

    @staticmethod
    def _a_star(grid: np.ndarray, start: tuple[int, int], end: tuple[int, int], suitability_weight: float, length_weight: float) -> list[tuple[int, int]]:
        height, width = grid.shape
        frontier: list[tuple[float, tuple[int, int]]] = [(0.0, start)]
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        cost_so_far: dict[tuple[int, int], float] = {start: 0.0}
        neighbours = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]
        while frontier:
            _, current = heapq.heappop(frontier)
            if current == end:
                break
            for dx, dy in neighbours:
                nx, ny = current[0] + dx, current[1] + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                step = math.sqrt(2.0) if dx and dy else 1.0
                suitability_cost = (1.0 - float(grid[ny, nx])) * suitability_weight
                new_cost = cost_so_far[current] + step * length_weight + suitability_cost
                candidate = (nx, ny)
                if candidate not in cost_so_far or new_cost < cost_so_far[candidate]:
                    cost_so_far[candidate] = new_cost
                    heuristic = math.hypot(end[0] - nx, end[1] - ny) * length_weight
                    heapq.heappush(frontier, (new_cost + heuristic, candidate))
                    came_from[candidate] = current
        if end not in came_from:
            return [start, end]
        path = []
        current: tuple[int, int] | None = end
        while current is not None:
            path.append(current)
            current = came_from[current]
        return list(reversed(path))

    def carbon_and_ecosystems(self, state: Any, tree_count: int, rainfall: dict[str, Any]) -> dict[str, Any]:
        veg = state.vegetation
        barrier = state.barrier
        mean_veg = float(np.mean(veg))
        dense_fraction = float(np.mean(veg >= 0.62))
        area_km2 = self._bbox_area_km2(self.settings.aoi_bbox)
        reference = self.settings.gedi_reference_agbd_mg_ha
        reference_unc = self.settings.gedi_reference_uncertainty_mg_ha
        if reference > 0:
            agbd = reference * (0.55 + mean_veg * 0.75)
            uncertainty = reference_unc if reference_unc > 0 else agbd * 0.30
            mode = "gedi_calibrated_context"
            note = "Biomass screening is scaled to the configured GEDI reference context."
        else:
            agbd = 5.0 + 33.0 * mean_veg + 18.0 * dense_fraction
            uncertainty = max(8.0, agbd * 0.45)
            mode = "modelled_screening"
            note = "No GEDI reference is configured; biomass is a broad NDVI/model-based screening estimate."
        hectares = area_km2 * 100.0
        biomass_mg = agbd * hectares
        carbon_t = biomass_mg * 0.47
        co2e_t = carbon_t * 44.0 / 12.0
        barrier_gain = float(np.mean(barrier)) * hectares * 0.9 + tree_count * 0.008
        annual_carbon_gain = barrier_gain * 0.47
        rain90 = float(rainfall.get("totals_mm", {}).get("90", 0.0))
        services = {
            "wind_erosion_protection": round(float(np.clip(mean_veg * 70 + np.mean(barrier) * 65, 0, 100)), 1),
            "water_infiltration_support": round(float(np.clip(mean_veg * 55 + rain90 / 8 + np.mean(barrier) * 30, 0, 100)), 1),
            "habitat_connectivity": round(float(np.clip(dense_fraction * 85 + np.mean(barrier) * 45, 0, 100)), 1),
            "settlement_shelter": round(float(np.clip(np.mean(barrier) * 220 + mean_veg * 30, 0, 100)), 1),
            "soil_retention": round(float(np.clip(mean_veg * 65 + np.mean(barrier) * 55, 0, 100)), 1),
        }
        return {
            "mode": mode,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "area_km2": round(area_km2, 1),
            "aboveground_biomass_density_mg_ha": round(agbd, 2),
            "uncertainty_mg_ha": round(uncertainty, 2),
            "estimated_total_carbon_t": round(carbon_t, 0),
            "estimated_total_co2e_t": round(co2e_t, 0),
            "scenario_annual_carbon_gain_t": round(annual_carbon_gain, 2),
            "ecosystem_service_scores": services,
            "note": note,
            "limitations": "These are scenario screening estimates with wide uncertainty and are not certified carbon-credit or ecosystem-service accounts.",
        }

    def risk_layers(self, state: Any, weather: Any, rainfall: dict[str, Any], fire: dict[str, Any]) -> dict[str, Any]:
        veg = state.vegetation.astype(np.float32)
        desert = state.desert.astype(np.float32)
        moisture = state.moisture.astype(np.float32)
        barrier = state.barrier.astype(np.float32)
        slope = self._normalise(np.hypot(*np.gradient(0.65 * desert - 0.25 * veg)))
        wind = float(np.clip(weather.wind_speed_mps / 12.0, 0.0, 1.0))
        rain = float(np.clip(weather.rain_1h_mm / 12.0, 0.0, 1.0))
        rain30 = float(np.clip(float(rainfall.get("totals_mm", {}).get("30", 0.0)) / 220.0, 0.0, 1.0))
        wind_erosion = np.clip((1.0 - veg) * desert * (0.35 + wind) * (1.0 - barrier * 0.75), 0, 1)
        runoff = np.clip((0.20 + rain + rain30 * 0.25) * slope * (1.0 - veg * 0.55) * (1.0 - moisture * 0.35), 0, 1)
        infiltration = np.clip(veg * 0.55 + moisture * 0.38 + barrier * 0.18 - slope * 0.12, 0, 1)
        fire_exposure = self._hotspot_penalty(veg.shape, fire.get("hotspots", []), self.settings.aoi_bbox)
        combined = np.clip(0.38 * wind_erosion + 0.28 * runoff + 0.20 * fire_exposure + 0.14 * (1.0 - infiltration), 0, 1)
        self._versions["risk"] += 1
        self._risk_texture = self._continuous_texture(combined, "risk")
        return {
            "mode": "derived_screening",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "wind_erosion_mean": round(float(np.mean(wind_erosion)), 4),
            "runoff_mean": round(float(np.mean(runoff)), 4),
            "infiltration_mean": round(float(np.mean(infiltration)), 4),
            "fire_exposure_mean": round(float(np.mean(fire_exposure)), 4),
            "combined_risk_mean": round(float(np.mean(combined)), 4),
            "texture_version": self._versions["risk"],
            "grid": combined.round(4).tolist(),
            "flow_vectors": self._flow_vectors(slope, runoff),
            "limitations": "Runoff and erosion use terrain-gradient and process proxies; they are not a calibrated hydrological or sediment-transport model.",
        }

    def compare_scenarios(self, state: Any) -> dict[str, Any]:
        presets = [
            ("No intervention", 0.62, 0.35, 0.20, 0.05, 0.20),
            ("Narrow maintained barrier", 0.58, 0.32, 0.34, 0.45, 0.72),
            ("Wide restoration corridor", 0.52, 0.26, 0.48, 0.72, 0.82),
            ("Drought and grazing stress", 0.82, 0.68, 0.12, 0.24, 0.40),
            ("Wet-year restoration", 0.38, 0.22, 0.72, 0.66, 0.78),
            ("Fire disturbance", 0.67, 0.30, 0.25, 0.48, 0.55),
        ]
        scenarios = []
        for index, (name, aridity, grazing, rainfall, restoration, maintenance) in enumerate(presets):
            vegetation = float(np.mean(state.vegetation))
            desert = float(np.mean(state.desert))
            barrier = float(np.mean(state.barrier))
            series = []
            for step in range(61):
                if step:
                    desert += 0.015 * aridity * (0.4 + desert) * (1 - vegetation) - 0.011 * restoration * rainfall * (0.3 + vegetation)
                    vegetation += 0.014 * rainfall * restoration * (1 - desert) * (1 - vegetation) - 0.011 * (aridity + grazing) * desert * vegetation
                    barrier += 0.018 * restoration * maintenance * (1 - desert) * max(0.02, barrier + 0.03) - 0.009 * (1 - maintenance) * desert
                    if name == "Fire disturbance" and step == 18:
                        vegetation *= 0.78
                        barrier *= 0.72
                    vegetation = float(np.clip(vegetation, 0, 1))
                    desert = float(np.clip(desert, 0, 1))
                    barrier = float(np.clip(barrier, 0, 1))
                series.append({"step": step, "vegetation": round(vegetation, 4), "desert": round(desert, 4), "barrier": round(barrier, 4)})
            scenarios.append({
                "id": index + 1,
                "name": name,
                "parameters": {"aridity": aridity, "grazing": grazing, "rainfall": rainfall, "restoration": restoration, "maintenance": maintenance},
                "series": series,
                "outcome": {
                    "vegetation_change": round(series[-1]["vegetation"] - series[0]["vegetation"], 4),
                    "desert_change": round(series[-1]["desert"] - series[0]["desert"], 4),
                    "barrier_change": round(series[-1]["barrier"] - series[0]["barrier"], 4),
                },
            })
        return {
            "mode": "scenario_experiment",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scenarios": scenarios,
            "limitations": "Scenario trajectories are transparent model experiments, not forecasts of actual land outcomes.",
        }

    def alerts(
        self,
        satellite: Any,
        simulation: Any,
        weather: Any,
        rainfall: dict[str, Any],
        fire: dict[str, Any],
        projects: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        drought = rainfall.get("drought_screen", {})
        if (drought.get("score") or 0) >= 65:
            items.append(self._alert("drought", "high", "Prolonged moisture deficit", f"Drought screening score is {drought.get('score')}/100."))
        if satellite.stats.mean < 0.18:
            items.append(self._alert("vegetation", "high", "Low observed greenness", f"Current mean NDVI is {satellite.stats.mean:.2f}."))
        if simulation.desert_fraction > 0.42:
            items.append(self._alert("model", "medium", "Expanding model desert pressure", f"{simulation.desert_fraction * 100:.1f}% of cells are in the high-pressure class."))
        if fire.get("hotspot_count", 0):
            items.append(self._alert("fire", "high", "Satellite thermal anomaly", f"{fire['hotspot_count']} FIRMS detections are present in the configured window."))
        if weather.wind_speed_mps >= 8 and simulation.desert_fraction > 0.25:
            items.append(self._alert("erosion", "medium", "Wind-erosion watch", f"Wind is {weather.wind_speed_mps:.1f} m/s while bare/high-pressure model cells are present."))
        for project in projects:
            inspections = project.get("inspections") or []
            if inspections and (inspections[0].get("survival_percent") or 100) < 55:
                items.append(self._alert("project", "high", f"Low survival: {project['name']}", f"Latest recorded survival is {inspections[0].get('survival_percent')}%."))
        if not items:
            items.append(self._alert("status", "low", "No high-priority platform alert", "Current screening thresholds did not trigger a high-priority alert."))
        return items

    @staticmethod
    def _alert(kind: str, severity: str, title: str, body: str) -> dict[str, Any]:
        return {"id": f"{kind}-{abs(hash((title, body))) % 100000}", "kind": kind, "severity": severity, "title": title, "body": body, "generated_at": datetime.now(timezone.utc).isoformat()}

    def landcover_texture(self) -> tuple[bytes, int]:
        return self._landcover_texture or array_to_rgba_png(np.zeros((2, 2, 4), dtype=np.uint8)), self._versions["landcover"]

    def suitability_texture(self) -> tuple[bytes, int]:
        return self._suitability_texture or array_to_rgba_png(np.zeros((2, 2, 4), dtype=np.uint8)), self._versions["suitability"]

    def risk_texture(self) -> tuple[bytes, int]:
        return self._risk_texture or array_to_rgba_png(np.zeros((2, 2, 4), dtype=np.uint8)), self._versions["risk"]

    @staticmethod
    def _continuous_texture(values: np.ndarray, palette: str) -> bytes:
        v = np.clip(values, 0, 1)
        rgba = np.zeros((*v.shape, 4), dtype=np.uint8)
        if palette == "suitability":
            rgba[..., 0] = np.clip(210 - v * 180, 0, 255)
            rgba[..., 1] = np.clip(70 + v * 170, 0, 255)
            rgba[..., 2] = np.clip(55 + v * 50, 0, 255)
        else:
            rgba[..., 0] = np.clip(45 + v * 210, 0, 255)
            rgba[..., 1] = np.clip(170 - v * 145, 0, 255)
            rgba[..., 2] = np.clip(90 - v * 55, 0, 255)
        rgba[..., 3] = np.clip(45 + v * 185, 0, 225).astype(np.uint8)
        return array_to_rgba_png(rgba)

    @staticmethod
    def _normalise(values: np.ndarray) -> np.ndarray:
        minimum = float(np.nanmin(values))
        maximum = float(np.nanmax(values))
        return (values - minimum) / max(maximum - minimum, 1e-6)

    @staticmethod
    def _resize(values: np.ndarray | None, height: int, width: int) -> np.ndarray:
        if values is None:
            return np.zeros((height, width), dtype=np.float32)
        y_indices = np.linspace(0, values.shape[0] - 1, height).round().astype(int)
        x_indices = np.linspace(0, values.shape[1] - 1, width).round().astype(int)
        return values[np.ix_(y_indices, x_indices)]

    @staticmethod
    def _settlement_access(shape: tuple[int, int], locations: dict[str, Any], bbox: tuple[float, float, float, float]) -> np.ndarray:
        height, width = shape
        output = np.zeros(shape, dtype=np.float32)
        west, south, east, north = bbox
        points = []
        for feature in locations.get("features", []):
            coordinates = (feature.get("geometry") or {}).get("coordinates")
            if coordinates and len(coordinates) >= 2:
                x = (float(coordinates[0]) - west) / max(east - west, 1e-9) * (width - 1)
                y = (north - float(coordinates[1])) / max(north - south, 1e-9) * (height - 1)
                points.append((x, y))
        if not points:
            return np.full(shape, 0.5, dtype=np.float32)
        yy, xx = np.mgrid[0:height, 0:width]
        distance = np.full(shape, np.inf, dtype=np.float32)
        for x, y in points:
            distance = np.minimum(distance, np.hypot(xx - x, yy - y))
        scale = max(height, width) * 0.24
        return np.exp(-distance / max(scale, 1.0)).astype(np.float32)

    @staticmethod
    def _hotspot_penalty(shape: tuple[int, int], hotspots: Iterable[dict[str, Any]], bbox: tuple[float, float, float, float]) -> np.ndarray:
        height, width = shape
        west, south, east, north = bbox
        yy, xx = np.mgrid[0:height, 0:width]
        output = np.zeros(shape, dtype=np.float32)
        for item in hotspots:
            longitude = float(item.get("longitude") or 0.0)
            latitude = float(item.get("latitude") or 0.0)
            x = (longitude - west) / max(east - west, 1e-9) * (width - 1)
            y = (north - latitude) / max(north - south, 1e-9) * (height - 1)
            frp = float(item.get("frp_mw") or 1.0)
            output = np.maximum(output, np.exp(-np.hypot(xx - x, yy - y) / max(2.5, min(width, height) * 0.08)) * np.clip(frp / 20.0, 0.25, 1.0))
        return np.clip(output, 0, 1).astype(np.float32)

    @staticmethod
    def _flow_vectors(slope: np.ndarray, runoff: np.ndarray) -> list[dict[str, float]]:
        gy, gx = np.gradient(slope)
        height, width = slope.shape
        vectors = []
        for row in range(3, height, max(4, height // 12)):
            for col in range(3, width, max(4, width // 16)):
                magnitude = float(runoff[row, col])
                if magnitude < 0.12:
                    continue
                vectors.append({"x": col / (width - 1), "y": row / (height - 1), "dx": round(float(gx[row, col]), 4), "dy": round(float(gy[row, col]), 4), "magnitude": round(magnitude, 4)})
        return vectors[:250]

    @staticmethod
    def _coordinate_to_cell(coord: tuple[float, float], bbox: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int]:
        west, south, east, north = bbox
        lon, lat = coord
        x = int(np.clip(round((lon - west) / max(east - west, 1e-9) * (width - 1)), 0, width - 1))
        y = int(np.clip(round((north - lat) / max(north - south, 1e-9) * (height - 1)), 0, height - 1))
        return x, y

    @staticmethod
    def _cell_to_coordinate(cell: tuple[int, int], bbox: tuple[float, float, float, float], width: int, height: int) -> list[float]:
        west, south, east, north = bbox
        x, y = cell
        lon = west + x / max(width - 1, 1) * (east - west)
        lat = north - y / max(height - 1, 1) * (north - south)
        return [round(lon, 6), round(lat, 6)]

    @staticmethod
    def _haversine(a: list[float], b: list[float]) -> float:
        radius = 6371.0088
        lon1, lat1 = map(math.radians, a)
        lon2, lat2 = map(math.radians, b)
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return radius * 2 * math.asin(min(1.0, math.sqrt(value)))

    @staticmethod
    def _bbox_area_km2(bbox: tuple[float, float, float, float]) -> float:
        west, south, east, north = bbox
        width = IntelligenceEngine._haversine([west, (south + north) / 2], [east, (south + north) / 2])
        height = IntelligenceEngine._haversine([(west + east) / 2, south], [(west + east) / 2, north])
        return width * height
