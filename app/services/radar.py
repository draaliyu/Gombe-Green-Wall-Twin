from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

import httpx
import numpy as np
import tifffile

from app.config import Settings
from app.services.texture import array_to_rgba_png

LOGGER = logging.getLogger("green-wall-twin.radar")

S1_EVALSCRIPT = r"""
//VERSION=3
function setup() {
  return {
    input: [{bands: ["VV", "VH", "dataMask"]}],
    output: {bands: 4, sampleType: "FLOAT32"}
  };
}
function evaluatePixel(sample) {
  const vv = Math.max(sample.VV, 0.000001);
  const vh = Math.max(sample.VH, 0.000001);
  const rvi = Math.min(1.0, Math.max(0.0, 4.0 * vh / (vv + vh)));
  return [vv, vh, rvi, sample.dataMask];
}
"""


class Sentinel1RadarService:
    """Cloud-independent Sentinel-1 backscatter context.

    The service returns radar vegetation/moisture *signals*. It does not claim
    direct soil-moisture measurements or vegetation biomass.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client
        self._token: str | None = None
        self._token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self._cache: dict[str, Any] | None = None
        self._texture: bytes | None = None
        self._version = 0
        self._lock = asyncio.Lock()

    async def initial_data(self) -> dict[str, Any]:
        if self.settings.has_copernicus_credentials:
            try:
                return await self.fetch_live()
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Initial Sentinel-1 request failed: %s", exc)
        return self._demo("Copernicus Sentinel-1 data are not available; a labelled derived radar proxy is active.")

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

    async def fetch_live(self) -> dict[str, Any]:
        async with self._lock:
            token = await self._get_token()
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=max(20, self.settings.sentinel_lookback_days))
            west, south, east, north = self.settings.aoi_bbox
            payload: dict[str, Any] = {
                "input": {
                    "bounds": {
                        "bbox": [west, south, east, north],
                        "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
                    },
                    "data": [{
                        "type": "sentinel-1-grd",
                        "dataFilter": {
                            "timeRange": {
                                "from": start.isoformat().replace("+00:00", "Z"),
                                "to": end.isoformat().replace("+00:00", "Z"),
                            },
                            "mosaickingOrder": "mostRecent",
                        },
                        "processing": {
                            "orthorectify": True,
                            "backCoeff": "GAMMA0_TERRAIN",
                        },
                    }],
                },
                "output": {
                    "width": self.settings.simulation_grid_width,
                    "height": self.settings.simulation_grid_height,
                    "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
                },
                "evalscript": S1_EVALSCRIPT,
            }
            response = await self.client.post(
                self.settings.copernicus_process_url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=120.0,
            )
            if response.status_code == 404 and "/process/v1" in self.settings.copernicus_process_url:
                fallback = self.settings.copernicus_process_url.replace("/process/v1", "/api/v1/process")
                response = await self.client.post(fallback, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=120.0)
            response.raise_for_status()
            array = tifffile.imread(BytesIO(response.content))
            if array.ndim == 3 and array.shape[-1] >= 4:
                vv, vh, rvi, mask = (array[..., index].astype(np.float32) for index in range(4))
            elif array.ndim == 3 and array.shape[0] >= 4:
                vv, vh, rvi, mask = (array[index].astype(np.float32) for index in range(4))
            else:
                raise ValueError(f"Unexpected Sentinel-1 TIFF shape: {array.shape}")
            valid = (mask > 0.5) & np.isfinite(rvi) & np.isfinite(vv) & np.isfinite(vh)
            if np.count_nonzero(valid) < max(50, int(valid.size * 0.02)):
                raise ValueError("Sentinel-1 response contained too few valid pixels")
            rvi = np.clip(rvi, 0.0, 1.0)
            vv_db = 10.0 * np.log10(np.clip(vv, 1e-6, None))
            vh_db = 10.0 * np.log10(np.clip(vh, 1e-6, None))
            self._version += 1
            self._texture = self._make_texture(rvi, vv_db, valid)
            self._cache = {
                "mode": "live",
                "fetched_at": end.isoformat(),
                "observation_window_start": start.isoformat(),
                "observation_window_end": end.isoformat(),
                "mean_vv_db": round(float(np.mean(vv_db[valid])), 3),
                "mean_vh_db": round(float(np.mean(vh_db[valid])), 3),
                "mean_rvi": round(float(np.mean(rvi[valid])), 4),
                "valid_fraction": round(float(np.mean(valid)), 4),
                "texture_version": self._version,
                "source": "Copernicus Data Space Sentinel-1 GRD Process API",
                "interpretation": self._interpretation(float(np.mean(rvi[valid])), float(np.mean(vv_db[valid]))),
                "limitations": (
                    "Sentinel-1 backscatter is sensitive to surface roughness, structure and moisture. "
                    "The displayed radar vegetation/moisture signal is not a direct soil-moisture or biomass measurement."
                ),
                "grid": rvi.round(4).tolist(),
                "valid": valid.astype(np.uint8).tolist(),
            }
            return self._cache

    def _demo(self, note: str) -> dict[str, Any]:
        height = self.settings.simulation_grid_height
        width = self.settings.simulation_grid_width
        y, x = np.mgrid[0:height, 0:width]
        rng = np.random.default_rng(self.settings.random_seed + 77)
        rvi = np.clip(0.25 + 0.22 * np.sin(x / 11.0) + 0.16 * np.cos(y / 8.0) + rng.normal(0, 0.04, (height, width)), 0.02, 0.88).astype(np.float32)
        vv_db = (-12.0 + 5.0 * rvi + rng.normal(0, 0.7, (height, width))).astype(np.float32)
        valid = np.ones((height, width), dtype=bool)
        self._version += 1
        self._texture = self._make_texture(rvi, vv_db, valid)
        self._cache = {
            "mode": "demo",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "observation_window_start": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
            "observation_window_end": datetime.now(timezone.utc).isoformat(),
            "mean_vv_db": round(float(np.mean(vv_db)), 3),
            "mean_vh_db": round(float(np.mean(vv_db - 6.5)), 3),
            "mean_rvi": round(float(np.mean(rvi)), 4),
            "valid_fraction": 1.0,
            "texture_version": self._version,
            "source": "Deterministic radar proxy",
            "interpretation": self._interpretation(float(np.mean(rvi)), float(np.mean(vv_db))),
            "limitations": note,
            "grid": rvi.round(4).tolist(),
            "valid": valid.astype(np.uint8).tolist(),
        }
        return self._cache

    @staticmethod
    def _make_texture(rvi: np.ndarray, vv_db: np.ndarray, valid: np.ndarray) -> bytes:
        moisture = np.clip((vv_db + 20.0) / 15.0, 0.0, 1.0)
        rgba = np.zeros((*rvi.shape, 4), dtype=np.uint8)
        rgba[..., 0] = np.clip(35 + rvi * 65, 0, 255).astype(np.uint8)
        rgba[..., 1] = np.clip(65 + rvi * 170, 0, 255).astype(np.uint8)
        rgba[..., 2] = np.clip(95 + moisture * 150, 0, 255).astype(np.uint8)
        rgba[..., 3] = np.where(valid, 205, 0).astype(np.uint8)
        return array_to_rgba_png(rgba)

    @staticmethod
    def _interpretation(mean_rvi: float, mean_vv_db: float) -> list[dict[str, str]]:
        structure = "stronger" if mean_rvi >= 0.55 else "moderate" if mean_rvi >= 0.34 else "limited"
        wetness = "higher" if mean_vv_db > -8.5 else "intermediate" if mean_vv_db > -13.0 else "lower"
        return [
            {
                "title": "Radar structure signal",
                "body": f"Mean radar vegetation index is {mean_rvi:.2f}, indicating {structure} cross-polarised structural response in this screening view.",
            },
            {
                "title": "Backscatter context",
                "body": f"Mean VV backscatter is {mean_vv_db:.1f} dB, a {wetness} relative backscatter level that can reflect several combinations of roughness, structure and moisture.",
            },
        ]

    async def texture(self) -> tuple[bytes, int]:
        if self._cache is None:
            await self.initial_data()
        assert self._texture is not None
        return self._texture, self._version
