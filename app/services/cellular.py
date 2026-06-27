from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from app.config import Settings
from app.models import ScenarioParameters, SimulationMetrics, TreeInstance
from app.services.texture import simulation_to_texture


def _neighbour_mean(array: np.ndarray) -> np.ndarray:
    total = np.zeros_like(array, dtype=np.float32)
    count = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            total += np.roll(np.roll(array, dy, axis=0), dx, axis=1)
            count += 1
    return total / float(count)


def _resize_nearest(array: np.ndarray, target_height: int, target_width: int) -> np.ndarray:
    y_indices = np.linspace(0, array.shape[0] - 1, target_height).round().astype(int)
    x_indices = np.linspace(0, array.shape[1] - 1, target_width).round().astype(int)
    return array[np.ix_(y_indices, x_indices)]


@dataclass(slots=True)
class AutomatonState:
    vegetation: np.ndarray
    desert: np.ndarray
    barrier: np.ndarray
    moisture: np.ndarray
    baseline_ndvi: np.ndarray


class DesertificationAutomaton:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.width = settings.simulation_grid_width
        self.height = settings.simulation_grid_height
        self.rng = np.random.default_rng(settings.random_seed)
        self.parameters = ScenarioParameters()
        self.running = True
        self.speed = 1.0
        self.tick = 0
        self.texture_version = 0
        self.tree_version = 0
        self._previous_desert_fraction = 0.0
        self._last_desert_change = 0.0
        self._initial_vegetated_fraction = 0.0
        blank = np.zeros((self.height, self.width), dtype=np.float32)
        self.state = AutomatonState(blank.copy(), blank.copy(), blank.copy(), blank.copy(), blank.copy())
        self._texture_png = simulation_to_texture(blank, blank, blank)
        self._trees: list[TreeInstance] = []

    @property
    def texture_png(self) -> bytes:
        return self._texture_png

    @property
    def trees(self) -> list[TreeInstance]:
        return self._trees

    def initialise_from_ndvi(self, ndvi: np.ndarray, valid: np.ndarray) -> None:
        values = _resize_nearest(ndvi, self.height, self.width).astype(np.float32)
        mask = _resize_nearest(valid.astype(np.float32), self.height, self.width) > 0.5
        fallback = float(np.nanmedian(values[mask])) if np.any(mask) else 0.2
        values = np.where(mask, values, fallback)
        normalised = np.clip((values + 0.05) / 0.72, 0.0, 1.0)
        vegetation = np.clip(normalised * 0.84, 0.02, 0.95)
        north_gradient = np.linspace(0.22, -0.05, self.height, dtype=np.float32)[:, None]
        desert = np.clip(0.78 - vegetation + north_gradient, 0.02, 0.95)
        moisture = np.clip(0.18 + normalised * 0.65, 0.05, 0.92)
        barrier = np.zeros_like(vegetation)
        # A sparse demonstration belt gives the simulator something visible before users design a corridor.
        belt_y = int(self.height * 0.46)
        belt_x0 = int(self.width * 0.12)
        belt_x1 = int(self.width * 0.88)
        barrier[max(0, belt_y - 1):min(self.height, belt_y + 2), belt_x0:belt_x1:3] = 0.56
        vegetation = np.clip(vegetation + barrier * 0.10, 0.0, 1.0)
        self.state = AutomatonState(vegetation, desert, barrier, moisture, values)
        self.tick = 0
        self._previous_desert_fraction = float(np.mean(desert > 0.60))
        self._last_desert_change = 0.0
        self._initial_vegetated_fraction = float(np.mean(vegetation > 0.38))
        self._refresh_visual_assets(force=True)

    def assimilate_ndvi(self, ndvi: np.ndarray, valid: np.ndarray) -> None:
        values = _resize_nearest(ndvi, self.height, self.width).astype(np.float32)
        mask = _resize_nearest(valid.astype(np.float32), self.height, self.width) > 0.5
        observation = np.clip((values + 0.05) / 0.72, 0.0, 1.0)
        self.state.vegetation = np.where(
            mask,
            np.clip(self.state.vegetation * 0.68 + observation * 0.32, 0.0, 1.0),
            self.state.vegetation,
        )
        self.state.moisture = np.where(
            mask,
            np.clip(self.state.moisture * 0.75 + (0.18 + observation * 0.65) * 0.25, 0.0, 1.0),
            self.state.moisture,
        )
        self.state.baseline_ndvi = np.where(mask, values, self.state.baseline_ndvi)
        self._refresh_visual_assets(force=True)

    def set_parameters(self, parameters: ScenarioParameters) -> None:
        self.parameters = parameters

    def set_running(self, running: bool) -> None:
        self.running = running

    def set_speed(self, speed: float) -> None:
        self.speed = float(np.clip(speed, 0.25, 5.0))

    def step(self, substeps: int = 1) -> None:
        if not self.running:
            return
        count = max(1, int(round(substeps * self.speed)))
        for _ in range(count):
            self._single_step()
        self._refresh_visual_assets(force=(self.tick % 2 == 0))

    def _single_step(self) -> None:
        p = self.parameters
        state = self.state
        neighbour_desert = _neighbour_mean(state.desert)
        neighbour_veg = _neighbour_mean(state.vegetation)
        neighbour_barrier = _neighbour_mean(state.barrier)

        pressure = 0.52 * p.aridity_pressure + 0.30 * p.grazing_pressure + 0.18 * (1.0 - p.rainfall_support)
        barrier_protection = np.clip(state.barrier * 0.78 + neighbour_barrier * 0.42, 0.0, 0.92)
        spread = (
            p.spread_rate
            * pressure
            * (0.28 + neighbour_desert)
            * (1.0 - state.vegetation * 0.68)
            * (1.0 - barrier_protection)
        )
        recovery = (
            p.restoration_effort
            * 0.025
            * (0.30 + state.moisture)
            * (0.20 + neighbour_veg)
            * (1.0 - state.desert)
        )
        desert_next = np.clip(state.desert + spread - recovery, 0.0, 1.0)

        growth = (
            p.growth_rate
            * (0.18 + p.rainfall_support * 0.62 + state.moisture * 0.35)
            * (0.18 + neighbour_veg)
            * (1.0 - desert_next * 0.72)
            * (1.0 - state.vegetation)
        )
        stress = (
            0.030
            * (0.42 * p.aridity_pressure + 0.40 * p.grazing_pressure + 0.18 * desert_next)
            * (0.20 + desert_next)
            * state.vegetation
        )
        restoration = 0.018 * p.restoration_effort * (state.barrier + neighbour_barrier * 0.35)
        vegetation_next = np.clip(state.vegetation + growth + restoration - stress, 0.0, 1.0)

        barrier_growth = (
            0.020
            * p.barrier_maintenance
            * p.restoration_effort
            * (0.25 + state.moisture)
            * (1.0 - desert_next * 0.80)
            * (state.barrier > 0.02)
        )
        barrier_loss = (
            0.015
            * (1.0 - p.barrier_maintenance)
            * (0.35 + desert_next)
            * state.barrier
        )
        barrier_next = np.clip(state.barrier + barrier_growth - barrier_loss, 0.0, 1.0)

        moisture_gain = 0.012 * p.rainfall_support + 0.006 * barrier_next
        moisture_loss = 0.010 * p.aridity_pressure + 0.007 * desert_next
        moisture_next = np.clip(state.moisture + moisture_gain - moisture_loss, 0.0, 1.0)

        noise = self.rng.normal(0.0, 0.0018, size=state.desert.shape).astype(np.float32)
        desert_next = np.clip(desert_next + noise, 0.0, 1.0)
        self.state = AutomatonState(
            vegetation_next.astype(np.float32),
            desert_next.astype(np.float32),
            barrier_next.astype(np.float32),
            moisture_next.astype(np.float32),
            state.baseline_ndvi,
        )
        current_desert_fraction = float(np.mean(self.state.desert > 0.60))
        self._last_desert_change = current_desert_fraction - self._previous_desert_fraction
        self._previous_desert_fraction = current_desert_fraction
        self.tick += 1

    def plant_corridor(self, coordinates: Iterable[tuple[float, float]], bbox: tuple[float, float, float, float], width_cells: int = 2) -> int:
        points = list(coordinates)
        if len(points) < 2:
            return 0
        west, south, east, north = bbox

        def to_cell(lon: float, lat: float) -> tuple[int, int]:
            x = int(round((lon - west) / max(east - west, 1e-9) * (self.width - 1)))
            y = int(round((north - lat) / max(north - south, 1e-9) * (self.height - 1)))
            return int(np.clip(x, 0, self.width - 1)), int(np.clip(y, 0, self.height - 1))

        changed: set[tuple[int, int]] = set()
        for start, end in zip(points[:-1], points[1:]):
            x0, y0 = to_cell(*start)
            x1, y1 = to_cell(*end)
            steps = max(abs(x1 - x0), abs(y1 - y0), 1)
            for index in range(steps + 1):
                t = index / steps
                x = int(round(x0 + (x1 - x0) * t))
                y = int(round(y0 + (y1 - y0) * t))
                for oy in range(-width_cells, width_cells + 1):
                    for ox in range(-width_cells, width_cells + 1):
                        if ox * ox + oy * oy > width_cells * width_cells:
                            continue
                        xx, yy = x + ox, y + oy
                        if 0 <= xx < self.width and 0 <= yy < self.height:
                            self.state.barrier[yy, xx] = max(self.state.barrier[yy, xx], 0.78)
                            self.state.vegetation[yy, xx] = max(self.state.vegetation[yy, xx], 0.44)
                            self.state.desert[yy, xx] *= 0.72
                            changed.add((xx, yy))
        self._refresh_visual_assets(force=True)
        return len(changed)

    def clear_barriers(self) -> None:
        self.state.barrier.fill(0.0)
        self._refresh_visual_assets(force=True)

    def metrics(self) -> SimulationMetrics:
        vegetation = self.state.vegetation
        desert = self.state.desert
        barrier = self.state.barrier
        current_desert = float(np.mean(desert > 0.60))
        current_vegetated = float(np.mean(vegetation > 0.38))
        front = (desert > 0.48) & (desert < 0.68) & (_neighbour_mean(desert) > 0.50)
        barrier_health_values = vegetation[barrier > 0.08]
        tree_health = float(np.mean(barrier_health_values)) if barrier_health_values.size else 0.0
        metrics = SimulationMetrics(
            tick=self.tick,
            vegetated_fraction=round(current_vegetated, 4),
            stressed_fraction=round(float(np.mean((vegetation >= 0.18) & (vegetation <= 0.38))), 4),
            bare_fraction=round(float(np.mean((vegetation < 0.18) & (desert < 0.60))), 4),
            desert_fraction=round(current_desert, 4),
            barrier_fraction=round(float(np.mean(barrier > 0.08)), 4),
            mean_tree_health=round(tree_health, 4),
            desert_front_cells=int(np.count_nonzero(front)),
            restoration_gain=round(current_vegetated - self._initial_vegetated_fraction, 4),
            desert_change=round(self._last_desert_change, 4),
        )
        return metrics

    def _refresh_visual_assets(self, force: bool = False) -> None:
        if force:
            self.texture_version += 1
            self._texture_png = simulation_to_texture(
                self.state.vegetation,
                self.state.desert,
                self.state.barrier,
            )
            self._rebuild_trees()

    def _rebuild_trees(self) -> None:
        west, south, east, north = self.settings.aoi_bbox
        candidates = np.argwhere((self.state.barrier > 0.10) | (self.state.vegetation > 0.68))
        if candidates.size == 0:
            self._trees = []
            return
        max_trees = 420
        stride = max(1, int(np.ceil(len(candidates) / max_trees)))
        selected = candidates[::stride][:max_trees]
        trees: list[TreeInstance] = []
        for tree_id, (row, col) in enumerate(selected):
            health = float(np.clip(self.state.vegetation[row, col] * 0.72 + self.state.barrier[row, col] * 0.38, 0.08, 1.0))
            lon = west + (col + 0.5) / self.width * (east - west)
            lat = north - (row + 0.5) / self.height * (north - south)
            jitter_x = ((tree_id * 37) % 101 - 50) / 101 * (east - west) / self.width * 0.55
            jitter_y = ((tree_id * 53) % 97 - 48) / 97 * (north - south) / self.height * 0.55
            trees.append(TreeInstance(
                id=tree_id,
                longitude=round(lon + jitter_x, 6),
                latitude=round(lat + jitter_y, 6),
                health=round(health, 4),
                height_m=round(2.2 + health * 8.6, 2),
                crown_m=round(1.0 + health * 3.6, 2),
                barrier=bool(self.state.barrier[row, col] > 0.10),
            ))
        self._trees = trees
        self.tree_version += 1
