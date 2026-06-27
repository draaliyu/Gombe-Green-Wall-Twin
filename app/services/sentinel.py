from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

import httpx
import numpy as np
import tifffile

from app.config import Settings
from app.models import NDVIStatistics, SatelliteSnapshot
from app.services.texture import ndvi_to_texture

LOGGER = logging.getLogger("green-wall-twin.sentinel")

NDVI_EVALSCRIPT = r"""
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "SCL", "dataMask"] }],
    output: { bands: 2, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(sample) {
  const invalid = [0, 1, 3, 8, 9, 10, 11].includes(sample.SCL);
  const denom = sample.B08 + sample.B04;
  const ndvi = denom === 0 ? -9999 : (sample.B08 - sample.B04) / denom;
  const valid = sample.dataMask === 1 && !invalid && Number.isFinite(ndvi);
  return [valid ? ndvi : -9999, valid ? 1 : 0];
}
"""


@dataclass(slots=True)
class SatelliteData:
    snapshot: SatelliteSnapshot
    ndvi: np.ndarray
    valid: np.ndarray
    texture_png: bytes


def calculate_stats(ndvi: np.ndarray, valid: np.ndarray) -> NDVIStatistics:
    values = ndvi[valid & np.isfinite(ndvi)]
    if values.size == 0:
        values = np.array([0.0], dtype=np.float32)
    total = max(int(ndvi.size), 1)
    valid_count = int(np.count_nonzero(valid))
    return NDVIStatistics(
        mean=round(float(np.mean(values)), 4),
        median=round(float(np.median(values)), 4),
        p10=round(float(np.percentile(values, 10)), 4),
        p90=round(float(np.percentile(values, 90)), 4),
        minimum=round(float(np.min(values)), 4),
        maximum=round(float(np.max(values)), 4),
        valid_fraction=round(valid_count / total, 4),
        bare_fraction=round(float(np.mean(values < 0.15)), 4),
        sparse_fraction=round(float(np.mean((values >= 0.15) & (values < 0.30))), 4),
        moderate_fraction=round(float(np.mean((values >= 0.30) & (values < 0.50))), 4),
        dense_fraction=round(float(np.mean(values >= 0.50)), 4),
    )


def generate_demo_ndvi(width: int, height: int, seed: int, now: datetime | None = None) -> tuple[np.ndarray, np.ndarray]:
    current = now or datetime.now(timezone.utc)
    rng = np.random.default_rng(seed + current.timetuple().tm_yday // 8)
    y, x = np.mgrid[0:height, 0:width]
    latitude_factor = 1.0 - (y / max(height - 1, 1))
    seasonal = 0.08 * np.sin((current.timetuple().tm_yday - 190) / 365.0 * np.pi * 2.0)
    river_corridor = 0.17 * np.exp(-((x - width * 0.64) / (width * 0.12)) ** 2)
    planted_belt = 0.11 * np.exp(-((y - height * 0.42) / (height * 0.07)) ** 2)
    dry_front = 0.22 * latitude_factor
    texture = (
        0.29
        + seasonal
        + river_corridor
        + planted_belt
        - dry_front
        + 0.05 * np.sin(x / 7.5)
        + 0.035 * np.cos(y / 5.0)
        + rng.normal(0.0, 0.025, size=(height, width))
    )
    ndvi = np.clip(texture, -0.08, 0.72).astype(np.float32)
    valid = np.ones_like(ndvi, dtype=bool)
    cloud_blob = ((x - width * 0.27) ** 2 / (width * 0.09) ** 2 + (y - height * 0.68) ** 2 / (height * 0.10) ** 2) < 1
    valid[cloud_blob & (rng.random((height, width)) > 0.45)] = False
    return ndvi, valid


class SentinelNDVIService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client
        self._token: str | None = None
        self._token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self._texture_version = 0
        self._lock = asyncio.Lock()

    async def initial_data(self) -> SatelliteData:
        demo = self._demo_data("Copernicus credentials are not configured; deterministic demonstration NDVI is active.")
        if self.settings.has_copernicus_credentials:
            try:
                return await self.fetch_live()
            except Exception as exc:  # noqa: BLE001 - service must fall back cleanly
                LOGGER.warning("Initial Sentinel-2 refresh failed; using demo data: %s", exc)
                demo.snapshot.note = f"Live Sentinel-2 request failed ({type(exc).__name__}); demonstration NDVI is active."
        return demo

    def _demo_data(self, note: str) -> SatelliteData:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.settings.sentinel_lookback_days)
        ndvi, valid = generate_demo_ndvi(
            self.settings.simulation_grid_width,
            self.settings.simulation_grid_height,
            self.settings.random_seed,
            end,
        )
        self._texture_version += 1
        snapshot = SatelliteSnapshot(
            mode="demo",
            fetched_at=end,
            observation_window_start=start,
            observation_window_end=end,
            grid_width=ndvi.shape[1],
            grid_height=ndvi.shape[0],
            cloud_limit_percent=self.settings.sentinel_max_cloud_percent,
            stats=calculate_stats(ndvi, valid),
            source_name="Deterministic demonstration surface",
            note=note,
            texture_version=self._texture_version,
        )
        return SatelliteData(snapshot, ndvi, valid, ndvi_to_texture(ndvi, valid))

    async def _get_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._token and now < self._token_expires_at - timedelta(seconds=60):
            return self._token
        response = await self.client.post(
            self.settings.copernicus_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.settings.copernicus_client_id,
                "client_secret": self.settings.copernicus_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        self._token = str(payload["access_token"])
        self._token_expires_at = now + timedelta(seconds=int(payload.get("expires_in", 600)))
        return self._token

    async def fetch_live(self) -> SatelliteData:
        async with self._lock:
            token = await self._get_token()
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=self.settings.sentinel_lookback_days)
            west, south, east, north = self.settings.aoi_bbox
            payload: dict[str, Any] = {
                "input": {
                    "bounds": {
                        "bbox": [west, south, east, north],
                        "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
                    },
                    "data": [{
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {
                                "from": start.isoformat().replace("+00:00", "Z"),
                                "to": end.isoformat().replace("+00:00", "Z"),
                            },
                            "maxCloudCoverage": self.settings.sentinel_max_cloud_percent,
                            "mosaickingOrder": "leastCC",
                        },
                    }],
                },
                "output": {
                    "width": self.settings.simulation_grid_width,
                    "height": self.settings.simulation_grid_height,
                    "responses": [{
                        "identifier": "default",
                        "format": {"type": "image/tiff"},
                    }],
                },
                "evalscript": NDVI_EVALSCRIPT,
            }
            response = await self.client.post(
                self.settings.copernicus_process_url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=90.0,
            )
            if response.status_code == 404 and "/process/v1" in self.settings.copernicus_process_url:
                fallback_url = self.settings.copernicus_process_url.replace("/process/v1", "/api/v1/process")
                response = await self.client.post(
                    fallback_url,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=90.0,
                )
            response.raise_for_status()
            array = tifffile.imread(BytesIO(response.content))
            if array.ndim == 3 and array.shape[-1] >= 2:
                ndvi = array[..., 0].astype(np.float32)
                valid = array[..., 1] > 0.5
            elif array.ndim == 3 and array.shape[0] >= 2:
                ndvi = array[0].astype(np.float32)
                valid = array[1] > 0.5
            else:
                raise ValueError(f"Unexpected Sentinel-2 TIFF shape: {array.shape}")
            valid &= np.isfinite(ndvi) & (ndvi > -2.0) & (ndvi <= 1.0)
            ndvi = np.clip(ndvi, -1.0, 1.0)
            if np.count_nonzero(valid) < max(50, int(ndvi.size * 0.03)):
                raise ValueError("Sentinel-2 response contained too few cloud-free pixels")
            self._texture_version += 1
            snapshot = SatelliteSnapshot(
                mode="live",
                fetched_at=end,
                observation_window_start=start,
                observation_window_end=end,
                grid_width=ndvi.shape[1],
                grid_height=ndvi.shape[0],
                cloud_limit_percent=self.settings.sentinel_max_cloud_percent,
                stats=calculate_stats(ndvi, valid),
                source_name="Copernicus Data Space Sentinel-2 L2A Process API",
                note=(
                    "NDVI is calculated from cloud-masked Sentinel-2 L2A red and near-infrared reflectance. "
                    "The timestamp is the API retrieval time; the request uses the least-cloudy observation within the displayed window."
                ),
                texture_version=self._texture_version,
            )
            return SatelliteData(snapshot, ndvi, valid, ndvi_to_texture(ndvi, valid))
