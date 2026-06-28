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


class WeatherSnapshot(BaseModel):
    mode: SourceMode
    fetched_at: datetime
    location_name: str
    longitude: float
    latitude: float
    temperature_c: float
    feels_like_c: float
    humidity_percent: float
    pressure_hpa: float
    wind_speed_mps: float
    wind_direction_deg: float
    wind_direction_cardinal: str
    wind_gust_mps: float | None = None
    cloud_cover_percent: float
    rain_1h_mm: float
    visibility_km: float | None = None
    condition: str
    weather_code: int
    sunrise: datetime
    sunset: datetime
    timezone_offset_seconds: int
    is_daylight: bool
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
    weather_moisture_forcing: float = 0.0
    weather_heat_stress: float = 0.0


class TreeInstance(BaseModel):
    id: int
    longitude: float
    latitude: float
    health: float
    height_m: float
    crown_m: float
    barrier: bool
    species_form: Literal["savanna", "shelterbelt", "shrub"] = "savanna"


class SimulationSnapshot(BaseModel):
    running: bool
    speed: float
    parameters: ScenarioParameters
    metrics: SimulationMetrics
    texture_version: int
    tree_version: int


class InsightItem(BaseModel):
    kind: Literal["observation", "external", "simulation", "interpretation", "limitation", "weather"]
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
    weather: WeatherSnapshot
    simulation: SimulationSnapshot
    insights: list[InsightItem]
