from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SourceMode = Literal["live", "demo", "mixed", "unavailable"]


class NDVIStatistics(BaseModel):
    mean: float
    median: float
    p10: float
    p90: float
    minimum: float
    maximum: float
    valid_fraction: float
    bare_fraction: float
    sparse_fraction: float
    moderate_fraction: float
    dense_fraction: float


class SatelliteSnapshot(BaseModel):
    mode: SourceMode
    fetched_at: datetime
    observation_window_start: datetime
    observation_window_end: datetime
    grid_width: int
    grid_height: int
    cloud_limit_percent: int
    stats: NDVIStatistics
    source_name: str
    note: str
    texture_version: int


class GFWYearLoss(BaseModel):
    year: int
    area_ha: float


class GFWSnapshot(BaseModel):
    mode: SourceMode
    fetched_at: datetime
    dataset: str
    dataset_version: str
    years: list[GFWYearLoss]
    cumulative_loss_ha: float
    latest_year_loss_ha: float
    note: str


class ScenarioParameters(BaseModel):
    aridity_pressure: float = Field(default=0.58, ge=0.0, le=1.0)
    grazing_pressure: float = Field(default=0.35, ge=0.0, le=1.0)
    rainfall_support: float = Field(default=0.35, ge=0.0, le=1.0)
    restoration_effort: float = Field(default=0.45, ge=0.0, le=1.0)
    barrier_maintenance: float = Field(default=0.70, ge=0.0, le=1.0)
    spread_rate: float = Field(default=0.055, ge=0.001, le=0.25)
    growth_rate: float = Field(default=0.040, ge=0.001, le=0.20)


class SimulationMetrics(BaseModel):
    tick: int
    vegetated_fraction: float
    stressed_fraction: float
    bare_fraction: float
    desert_fraction: float
    barrier_fraction: float
    mean_tree_health: float
    desert_front_cells: int
    restoration_gain: float
    desert_change: float


class TreeInstance(BaseModel):
    id: int
    longitude: float
    latitude: float
    health: float
    height_m: float
    crown_m: float
    barrier: bool


class SimulationSnapshot(BaseModel):
    running: bool
    speed: float
    parameters: ScenarioParameters
    metrics: SimulationMetrics
    texture_version: int
    tree_version: int


class InsightItem(BaseModel):
    kind: Literal["observation", "external", "simulation", "interpretation", "limitation"]
    title: str
    body: str
    evidence: list[str] = []
    confidence: Literal["high", "medium", "low", "not-applicable"] = "not-applicable"


class TwinFrame(BaseModel):
    sequence: int
    generated_at: datetime
    source_mode: SourceMode
    satellite: SatelliteSnapshot
    gfw: GFWSnapshot
    simulation: SimulationSnapshot
    insights: list[InsightItem]
