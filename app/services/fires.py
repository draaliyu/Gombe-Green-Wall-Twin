from __future__ import annotations

import csv
import io
import logging
import math
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings

LOGGER = logging.getLogger("green-wall-twin.fires")


class FIRMSService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client
        self._cache: dict[str, Any] | None = None
        self._cached_at = datetime.min.replace(tzinfo=timezone.utc)

    async def fetch(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        if self._cache and (now - self._cached_at).total_seconds() < self.settings.firms_refresh_seconds:
            return self._cache
        if not self.settings.has_firms_credentials:
            self._cache = self._demo_or_unavailable("NASA_FIRMS_MAP_KEY is not configured")
            self._cached_at = now
            return self._cache
        west, south, east, north = self.settings.aoi_bbox
        url = self.settings.nasa_firms_area_url.format(
            map_key=self.settings.nasa_firms_map_key,
            source=self.settings.nasa_firms_source,
            bbox=f"{west},{south},{east},{north}",
            days=self.settings.firms_day_range,
        )
        try:
            response = await self.client.get(url, timeout=45.0)
            response.raise_for_status()
            rows = list(csv.DictReader(io.StringIO(response.text)))
            hotspots = [self._parse_row(row) for row in rows]
            hotspots = [item for item in hotspots if item is not None]
            self._cache = self._summarise(hotspots, "live", "NASA FIRMS area API")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("FIRMS request failed: %s", exc)
            self._cache = self._demo_or_unavailable(f"NASA FIRMS request failed ({type(exc).__name__})")
        self._cached_at = now
        return self._cache

    def _demo_or_unavailable(self, reason: str) -> dict[str, Any]:
        if not self.settings.enable_demo_data:
            return self._summarise([], "unavailable", "Unavailable", reason)
        west, south, east, north = self.settings.aoi_bbox
        hotspots = [
            {
                "latitude": south + (north - south) * 0.62,
                "longitude": west + (east - west) * 0.29,
                "frp_mw": 7.5,
                "brightness_k": 327.0,
                "confidence": "nominal",
                "acquired_at": datetime.now(timezone.utc).isoformat(),
                "satellite": "DEMO",
            },
            {
                "latitude": south + (north - south) * 0.48,
                "longitude": west + (east - west) * 0.72,
                "frp_mw": 3.1,
                "brightness_k": 318.0,
                "confidence": "low",
                "acquired_at": datetime.now(timezone.utc).isoformat(),
                "satellite": "DEMO",
            },
        ]
        return self._summarise(hotspots, "demo", "Deterministic thermal-anomaly demonstration", reason)

    @staticmethod
    def _parse_row(row: dict[str, str]) -> dict[str, Any] | None:
        try:
            latitude = float(row.get("latitude") or "nan")
            longitude = float(row.get("longitude") or "nan")
            if not math.isfinite(latitude) or not math.isfinite(longitude):
                return None
            date_text = row.get("acq_date") or ""
            time_text = (row.get("acq_time") or "0000").zfill(4)
            acquired = f"{date_text}T{time_text[:2]}:{time_text[2:]}:00Z" if date_text else datetime.now(timezone.utc).isoformat()
            return {
                "latitude": latitude,
                "longitude": longitude,
                "frp_mw": round(float(row.get("frp") or 0.0), 3),
                "brightness_k": round(float(row.get("bright_ti4") or row.get("brightness") or 0.0), 2),
                "confidence": str(row.get("confidence") or "not reported"),
                "acquired_at": acquired,
                "satellite": str(row.get("satellite") or row.get("instrument") or "unknown"),
            }
        except (TypeError, ValueError):
            return None

    def _summarise(self, hotspots: list[dict[str, Any]], mode: str, source: str, reason: str = "") -> dict[str, Any]:
        total_frp = sum(float(item.get("frp_mw") or 0.0) for item in hotspots)
        peak_frp = max([float(item.get("frp_mw") or 0.0) for item in hotspots] or [0.0])
        return {
            "mode": mode,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "hotspots": hotspots,
            "hotspot_count": len(hotspots),
            "total_frp_mw": round(total_frp, 3),
            "peak_frp_mw": round(peak_frp, 3),
            "interpretation": (
                "Satellite thermal anomalies are present in the analysis window. They may represent vegetation fire, "
                "open burning or another heat source; the API does not establish cause."
                if hotspots
                else "No thermal anomalies are present in the current returned window. This does not prove that no fire exists."
            ),
            "limitations": (
                f"{reason}. " if reason else ""
            ) + "FIRMS detections are satellite thermal anomalies, not field-confirmed fire incidents or air-temperature measurements.",
        }
