from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
import numpy as np

from app.config import Settings

LOGGER = logging.getLogger("green-wall-twin.rainfall")


class RainfallDroughtService:
    """Historical rainfall and drought-screening service.

    Live mode uses the Open-Meteo Historical Weather API. The derived drought
    indicators are screening metrics, not an official drought declaration.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client
        self._cache: dict[tuple[float, float], tuple[datetime, dict[str, Any]]] = {}

    async def fetch(self, longitude: float, latitude: float) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        cache_key = (round(float(longitude), 2), round(float(latitude), 2))
        cached = self._cache.get(cache_key)
        if cached and (now - cached[0]).total_seconds() < self.settings.rainfall_refresh_seconds:
            return cached[1]
        end = date.today() - timedelta(days=2)
        start = end - timedelta(days=self.settings.rainfall_history_days - 1)
        try:
            response = await self.client.get(
                self.settings.open_meteo_archive_url,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "daily": (
                        "precipitation_sum,temperature_2m_max,temperature_2m_min,"
                        "et0_fao_evapotranspiration,soil_moisture_0_to_7cm_mean"
                    ),
                    "timezone": "Africa/Lagos",
                },
                timeout=45.0,
            )
            response.raise_for_status()
            payload = response.json()
            result = self._summarise(payload, "live", "Open-Meteo historical reanalysis")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Historical rainfall request failed: %s", exc)
            if not self.settings.enable_demo_data:
                result = self._unavailable(str(exc))
            else:
                result = self._demo(longitude, latitude, start, end, type(exc).__name__)
        self._cache[cache_key] = (now, result)
        return result

    def _summarise(self, payload: dict[str, Any], mode: str, source: str) -> dict[str, Any]:
        daily = payload.get("daily") or {}
        times = daily.get("time") or []
        rain = np.asarray(daily.get("precipitation_sum") or [], dtype=np.float64)
        tmax = np.asarray(daily.get("temperature_2m_max") or [], dtype=np.float64)
        tmin = np.asarray(daily.get("temperature_2m_min") or [], dtype=np.float64)
        et0 = np.asarray(daily.get("et0_fao_evapotranspiration") or [], dtype=np.float64)
        soil = np.asarray(daily.get("soil_moisture_0_to_7cm_mean") or [], dtype=np.float64)
        length = min(len(times), rain.size)
        if length < 30:
            raise ValueError("Historical weather response contains too few daily observations")
        times = times[:length]
        rain = np.nan_to_num(rain[:length], nan=0.0)
        tmax = self._align(tmax, length)
        tmin = self._align(tmin, length)
        et0 = self._align(et0, length)
        soil = self._align(soil, length)
        records = [
            {
                "date": times[index],
                "rain_mm": round(float(rain[index]), 2),
                "tmax_c": round(float(tmax[index]), 2) if np.isfinite(tmax[index]) else None,
                "tmin_c": round(float(tmin[index]), 2) if np.isfinite(tmin[index]) else None,
                "et0_mm": round(float(et0[index]), 2) if np.isfinite(et0[index]) else None,
                "soil_moisture": round(float(soil[index]), 4) if np.isfinite(soil[index]) else None,
            }
            for index in range(max(0, length - 365), length)
        ]
        totals = {window: round(float(np.sum(rain[-window:])), 2) for window in (7, 30, 90, 365) if length >= window}
        dry_days = self._consecutive_dry_days(rain)
        monthly = self._monthly(rain, times)
        latest_month = monthly[-1]["rain_mm"] if monthly else 0.0
        historical_same_month = [item["rain_mm"] for item in monthly[:-1] if item["month"] == (monthly[-1]["month"] if monthly else 0)]
        baseline = float(np.mean(historical_same_month)) if historical_same_month else float(np.mean([m["rain_mm"] for m in monthly])) if monthly else 0.0
        anomaly_pct = ((latest_month - baseline) / baseline * 100.0) if baseline > 0 else 0.0
        water_balance = float(np.nansum(rain[-30:]) - np.nansum(et0[-30:])) if length >= 30 else 0.0
        severity = self._severity(totals.get(90, 0.0), anomaly_pct, dry_days, water_balance)
        onset = self._rainy_season_onset(rain, times)
        return {
            "mode": mode,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "daily": records,
            "monthly": monthly[-36:],
            "totals_mm": {str(key): value for key, value in totals.items()},
            "consecutive_dry_days": dry_days,
            "latest_month_anomaly_percent": round(anomaly_pct, 1),
            "water_balance_30d_mm": round(water_balance, 1),
            "soil_moisture_latest": round(float(soil[-1]), 4) if soil.size and np.isfinite(soil[-1]) else None,
            "rainy_season_onset": onset,
            "drought_screen": severity,
            "interpretation": self._interpretation(severity, dry_days, anomaly_pct, water_balance),
            "limitations": (
                "The drought category is a platform screening indicator derived from rainfall, evapotranspiration, "
                "soil-moisture and dry-day evidence. It is not an official meteorological drought declaration."
            ),
        }

    @staticmethod
    def _align(values: np.ndarray, length: int) -> np.ndarray:
        if values.size >= length:
            return values[:length]
        output = np.full(length, np.nan, dtype=np.float64)
        output[: values.size] = values
        return output

    @staticmethod
    def _consecutive_dry_days(rain: np.ndarray, threshold: float = 1.0) -> int:
        count = 0
        for value in rain[::-1]:
            if value < threshold:
                count += 1
            else:
                break
        return count

    @staticmethod
    def _monthly(rain: np.ndarray, times: list[str]) -> list[dict[str, Any]]:
        grouped: dict[str, float] = {}
        for timestamp, value in zip(times, rain, strict=False):
            key = timestamp[:7]
            grouped[key] = grouped.get(key, 0.0) + float(value)
        return [
            {"period": key, "year": int(key[:4]), "month": int(key[5:7]), "rain_mm": round(value, 2)}
            for key, value in sorted(grouped.items())
        ]

    @staticmethod
    def _rainy_season_onset(rain: np.ndarray, times: list[str]) -> str | None:
        # Screening definition: first three-day window after March with >=20 mm,
        # followed by no seven-day dry spell in the next 21 days.
        for index in range(2, len(rain) - 21):
            current = datetime.fromisoformat(times[index]).date()
            if current.month < 3:
                continue
            if float(np.sum(rain[index - 2 : index + 1])) < 20.0:
                continue
            future = rain[index + 1 : index + 22]
            longest = 0
            run = 0
            for value in future:
                if value < 1.0:
                    run += 1
                    longest = max(longest, run)
                else:
                    run = 0
            if longest < 7:
                return current.isoformat()
        return None

    @staticmethod
    def _severity(rain90: float, anomaly: float, dry_days: int, water_balance: float) -> dict[str, Any]:
        score = 0.0
        score += np.clip((180.0 - rain90) / 180.0, 0.0, 1.0) * 35.0
        score += np.clip((-anomaly) / 60.0, 0.0, 1.0) * 25.0
        score += np.clip(dry_days / 30.0, 0.0, 1.0) * 25.0
        score += np.clip((-water_balance) / 160.0, 0.0, 1.0) * 15.0
        score = float(np.clip(score, 0.0, 100.0))
        category = "low" if score < 25 else "watch" if score < 45 else "moderate" if score < 65 else "high" if score < 82 else "severe"
        return {"score": round(score, 1), "category": category}

    @staticmethod
    def _interpretation(severity: dict[str, Any], dry_days: int, anomaly: float, balance: float) -> list[dict[str, str]]:
        return [
            {
                "title": "Rainfall departure",
                "body": f"The latest monthly rainfall is {abs(anomaly):.1f}% {'below' if anomaly < 0 else 'above'} its same-month/reference baseline.",
                "kind": "observation",
            },
            {
                "title": "Dry spell",
                "body": f"The current sequence contains {dry_days} consecutive days below 1 mm rainfall.",
                "kind": "observation",
            },
            {
                "title": "Atmospheric water balance",
                "body": f"The 30-day rainfall-minus-reference-evapotranspiration balance is {balance:.1f} mm.",
                "kind": "calculated",
            },
            {
                "title": "Screening result",
                "body": f"The combined drought screening score is {severity['score']:.1f}/100 ({severity['category']}). Field and official agency evidence are still required.",
                "kind": "interpretation",
            },
        ]

    def _demo(self, longitude: float, latitude: float, start: date, end: date, reason: str) -> dict[str, Any]:
        days = (end - start).days + 1
        rng = np.random.default_rng(self.settings.random_seed + int(abs(longitude * 100 + latitude * 10)))
        times: list[str] = []
        rain: list[float] = []
        tmax: list[float] = []
        tmin: list[float] = []
        et0: list[float] = []
        soil: list[float] = []
        moisture = 0.18
        for offset in range(days):
            current = start + timedelta(days=offset)
            phase = math.sin((current.timetuple().tm_yday - 145) / 365.0 * math.tau)
            wet_probability = float(np.clip(0.14 + 0.36 * max(0.0, phase), 0.05, 0.62))
            amount = float(rng.gamma(1.7, 6.5)) if rng.random() < wet_probability else 0.0
            high = 34.0 - 4.2 * max(0.0, phase) + rng.normal(0.0, 1.2)
            low = high - 10.0 + rng.normal(0.0, 0.7)
            evap = 4.8 + max(0.0, high - 30.0) * 0.17
            moisture = float(np.clip(moisture * 0.92 + amount * 0.004 - evap * 0.0018, 0.04, 0.42))
            times.append(current.isoformat())
            rain.append(amount)
            tmax.append(high)
            tmin.append(low)
            et0.append(evap)
            soil.append(moisture)
        payload = {"daily": {"time": times, "precipitation_sum": rain, "temperature_2m_max": tmax, "temperature_2m_min": tmin, "et0_fao_evapotranspiration": et0, "soil_moisture_0_to_7cm_mean": soil}}
        result = self._summarise(payload, "demo", "Deterministic seasonal demonstration series")
        result["limitations"] = f"Live historical weather retrieval failed ({reason}); the displayed series is deterministic demonstration data and not an observation."
        return result

    @staticmethod
    def _unavailable(reason: str) -> dict[str, Any]:
        return {
            "mode": "unavailable",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "Unavailable",
            "daily": [],
            "monthly": [],
            "totals_mm": {},
            "consecutive_dry_days": None,
            "latest_month_anomaly_percent": None,
            "water_balance_30d_mm": None,
            "soil_moisture_latest": None,
            "rainy_season_onset": None,
            "drought_screen": {"score": None, "category": "unavailable"},
            "interpretation": [],
            "limitations": f"Historical rainfall service unavailable: {reason}",
        }
