from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _parse_bbox(value: object) -> tuple[float, float, float, float]:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("AOI_BBOX cannot be empty")
        if text[0] in "[(" and text[-1] in ")]":
            text = text[1:-1]
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                value = parsed
            else:
                value = [part.strip() for part in text.split(",")]
        except json.JSONDecodeError:
            value = [part.strip() for part in text.split(",")]
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("AOI_BBOX must contain west,south,east,north")
    west, south, east, north = (float(item) for item in value)
    if not (-180 <= west < east <= 180):
        raise ValueError("AOI_BBOX longitude order/range is invalid")
    if not (-90 <= south < north <= 90):
        raise ValueError("AOI_BBOX latitude order/range is invalid")
    return west, south, east, north


BBox = Annotated[tuple[float, float, float, float], NoDecode, BeforeValidator(_parse_bbox)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Gombe Desertification & Afforestation Intelligence Twin"
    app_version: str = "5.0.0"
    debug: bool = False
    enable_demo_data: bool = True

    # Sentinel-2 and Sentinel-1 through Copernicus Data Space Sentinel Hub.
    copernicus_client_id: str = ""
    copernicus_client_secret: str = ""
    copernicus_token_url: str = (
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    )
    copernicus_process_url: str = "https://sh.dataspace.copernicus.eu/process/v1"

    # Global Forest Watch.
    gfw_api_key: str = ""
    gfw_origin: str = ""
    gfw_dataset: str = "umd_tree_cover_loss"
    gfw_dataset_version: str = "latest"

    # Current weather and map tiles.
    openweather_api_key: str = ""
    openweather_current_url: str = "https://api.openweathermap.org/data/2.5/weather"
    openweather_forecast_url: str = "https://api.openweathermap.org/data/2.5/forecast"
    openweather_tile_url: str = "https://tile.openweathermap.org/map/{layer}/{z}/{x}/{y}.png"
    weather_refresh_seconds: int = Field(default=300, ge=60)
    weather_cache_seconds: int = Field(default=240, ge=30)

    # Historical rainfall and drought context. Open-Meteo does not require a key.
    open_meteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    rainfall_history_days: int = Field(default=730, ge=90, le=3650)
    rainfall_refresh_seconds: int = Field(default=21600, ge=900)

    # NASA FIRMS fire/thermal anomalies.
    nasa_firms_map_key: str = ""
    nasa_firms_source: str = "VIIRS_SNPP_NRT"
    nasa_firms_area_url: str = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{source}/{bbox}/{days}"
    firms_day_range: int = Field(default=3, ge=1, le=10)
    firms_refresh_seconds: int = Field(default=3600, ge=600)

    # Optional externally prepared live products. When absent, the platform uses
    # transparent derived layers and labels them as modelled rather than observed.
    dynamic_world_stats_url: str = ""
    dynamic_world_bearer_token: str = ""
    gedi_context_url: str = ""
    gedi_bearer_token: str = ""
    gedi_reference_agbd_mg_ha: float = Field(default=0.0, ge=0.0)
    gedi_reference_uncertainty_mg_ha: float = Field(default=0.0, ge=0.0)

    # Study area and scheduled updates.
    aoi_bbox: BBox = (10.55, 10.20, 11.85, 11.55)
    sentinel_lookback_days: int = Field(default=35, ge=5, le=180)
    sentinel_max_cloud_percent: int = Field(default=35, ge=0, le=100)
    satellite_refresh_seconds: int = Field(default=21600, ge=300)
    radar_refresh_seconds: int = Field(default=21600, ge=900)
    gfw_refresh_seconds: int = Field(default=43200, ge=600)
    simulation_interval_seconds: float = Field(default=1.0, ge=0.2, le=30.0)
    broadcast_interval_seconds: float = Field(default=1.0, ge=0.2, le=10.0)
    simulation_grid_width: int = Field(default=96, ge=32, le=192)
    simulation_grid_height: int = Field(default=72, ge=24, le=160)
    random_seed: int = 4106

    # Protected administrative actions: model retraining, temporal backfill,
    # field verification and project-registry writes.
    admin_password: str = ""
    admin_password_sha256: str = ""
    admin_token_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    prediction_min_samples: int = Field(default=24, ge=8, le=500)

    data_dir: Path = Path("data")
    cache_dir: Path = Path("data/cache")
    database_path: Path = Path("data/twin.sqlite3")
    model_path: Path = Path("data/prediction_model.json")

    @property
    def has_copernicus_credentials(self) -> bool:
        return bool(self.copernicus_client_id and self.copernicus_client_secret)

    @property
    def has_gfw_credentials(self) -> bool:
        return bool(self.gfw_api_key)

    @property
    def has_weather_credentials(self) -> bool:
        return bool(self.openweather_api_key)

    @property
    def has_firms_credentials(self) -> bool:
        return bool(self.nasa_firms_map_key)

    @property
    def has_admin_credentials(self) -> bool:
        return bool(self.admin_password or self.admin_password_sha256)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.model_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
