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

    app_name: str = "Northern Gombe Desertification & Afforestation Twin"
    app_version: str = "1.0.0"
    debug: bool = False

    copernicus_client_id: str = ""
    copernicus_client_secret: str = ""
    copernicus_token_url: str = (
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    )
    copernicus_process_url: str = "https://sh.dataspace.copernicus.eu/process/v1"

    gfw_api_key: str = ""
    gfw_origin: str = ""
    gfw_dataset: str = "umd_tree_cover_loss"
    gfw_dataset_version: str = "latest"

    aoi_bbox: BBox = (10.55, 10.20, 11.85, 11.55)
    sentinel_lookback_days: int = Field(default=35, ge=5, le=180)
    sentinel_max_cloud_percent: int = Field(default=35, ge=0, le=100)
    satellite_refresh_seconds: int = Field(default=21600, ge=300)
    gfw_refresh_seconds: int = Field(default=43200, ge=600)
    simulation_interval_seconds: float = Field(default=1.0, ge=0.2, le=30.0)
    broadcast_interval_seconds: float = Field(default=1.0, ge=0.2, le=10.0)
    simulation_grid_width: int = Field(default=96, ge=32, le=192)
    simulation_grid_height: int = Field(default=72, ge=24, le=160)
    random_seed: int = 4106

    data_dir: Path = Path("data")
    cache_dir: Path = Path("data/cache")

    @property
    def has_copernicus_credentials(self) -> bool:
        return bool(self.copernicus_client_id and self.copernicus_client_secret)

    @property
    def has_gfw_credentials(self) -> bool:
        return bool(self.gfw_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    return settings
