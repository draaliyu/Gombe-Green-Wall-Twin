from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import Settings
from app.models import WeatherForecastPoint, WeatherForecastSnapshot, WeatherSnapshot

LOGGER = logging.getLogger("green-wall-twin.weather")
ALLOWED_WEATHER_LAYERS = {"clouds_new", "precipitation_new", "pressure_new", "wind_new", "temp_new"}


def _wind_cardinal(degrees: float) -> str:
    labels = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return labels[int((degrees % 360) / 22.5 + 0.5) % 16]


def _demo_weather(longitude: float, latitude: float, name: str, reason: str) -> WeatherSnapshot:
    now = datetime.now(timezone.utc)
    local_hour = (now.hour + 1 + now.minute / 60) % 24
    day_phase = math.sin((local_hour - 6) / 12 * math.pi)
    temperature = 27.5 + max(0.0, day_phase) * 9.5 + (latitude - 10.3) * 0.7
    humidity = 56 - max(0.0, day_phase) * 24 + math.sin(now.timestamp() / 1600) * 4
    wind_direction = (48 + math.sin(now.timestamp() / 2200) * 24) % 360
    cloud_cover = max(4.0, min(78.0, 30 + math.sin(now.timestamp() / 1800 + longitude) * 24))
    rain = 0.0 if cloud_cover < 64 else max(0.0, (cloud_cover - 62) / 25)
    sunrise = now.replace(hour=4, minute=50, second=0, microsecond=0)
    sunset = now.replace(hour=17, minute=27, second=0, microsecond=0)
    is_daylight = sunrise <= now <= sunset
    return WeatherSnapshot(
        mode="demo",
        fetched_at=now,
        location_name=name,
        longitude=longitude,
        latitude=latitude,
        temperature_c=round(temperature, 1),
        feels_like_c=round(temperature + max(0.0, humidity - 50) * 0.03, 1),
        humidity_percent=round(max(10.0, min(100.0, humidity)), 1),
        pressure_hpa=round(1008 + math.sin(now.timestamp() / 3000) * 3, 1),
        wind_speed_mps=round(3.2 + abs(math.sin(now.timestamp() / 900)) * 3.1, 1),
        wind_direction_deg=round(wind_direction, 1),
        wind_direction_cardinal=_wind_cardinal(wind_direction),
        wind_gust_mps=round(5.2 + abs(math.sin(now.timestamp() / 700)) * 3.5, 1),
        cloud_cover_percent=round(cloud_cover, 1),
        rain_1h_mm=round(rain, 2),
        visibility_km=round(8.5 + (100 - cloud_cover) / 30, 1),
        condition="Light rain" if rain > 0 else "Partly cloudy" if cloud_cover > 35 else "Clear",
        weather_code=500 if rain > 0 else 802 if cloud_cover > 35 else 800,
        sunrise=sunrise,
        sunset=sunset,
        timezone_offset_seconds=3600,
        is_daylight=is_daylight,
        note=f"Demonstration weather is active because {reason}. It is not an observation.",
    )


def _demo_forecast(longitude: float, latitude: float, name: str, reason: str) -> WeatherForecastSnapshot:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    points: list[WeatherForecastPoint] = []
    for index in range(24):
        timestamp = now + timedelta(hours=index * 3)
        local_hour = (timestamp.hour + 1) % 24
        daylight = max(0.0, math.sin((local_hour - 6) / 12 * math.pi))
        cloud = max(4.0, min(88.0, 34 + math.sin(index * 0.58 + longitude) * 28))
        rain = max(0.0, (cloud - 67) / 13) if cloud > 67 else 0.0
        direction = (50 + math.sin(index / 4) * 35) % 360
        temperature = 25.0 + daylight * 10.5 + math.sin(index / 2.8) * 1.2
        humidity = max(18.0, min(92.0, 68 - daylight * 33 + math.cos(index / 3) * 8))
        points.append(WeatherForecastPoint(
            timestamp=timestamp,
            temperature_c=round(temperature, 1),
            feels_like_c=round(temperature + max(0.0, humidity - 55) * 0.025, 1),
            humidity_percent=round(humidity, 1),
            pressure_hpa=round(1008 + math.sin(index / 4) * 4, 1),
            wind_speed_mps=round(2.8 + abs(math.sin(index / 3)) * 4.0, 1),
            wind_direction_deg=round(direction, 1),
            wind_direction_cardinal=_wind_cardinal(direction),
            cloud_cover_percent=round(cloud, 1),
            precipitation_probability=round(min(1.0, rain / 3.0), 3),
            rain_3h_mm=round(rain, 2),
            condition="Rain" if rain > 0.15 else "Cloudy" if cloud > 55 else "Partly cloudy" if cloud > 25 else "Clear",
            weather_code=500 if rain > 0.15 else 803 if cloud > 55 else 802 if cloud > 25 else 800,
        ))
    return WeatherForecastSnapshot(
        mode="demo",
        fetched_at=datetime.now(timezone.utc),
        location_name=name,
        longitude=longitude,
        latitude=latitude,
        points=points,
        note=f"Demonstration forecast is active because {reason}. It is not a provider forecast.",
    )


class WeatherService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client
        self._cache: dict[str, WeatherSnapshot] = {}
        self._forecast_cache: dict[str, WeatherForecastSnapshot] = {}

    async def fetch(self, longitude: float, latitude: float, name: str = "Northern Gombe") -> WeatherSnapshot:
        key = f"{longitude:.3f}:{latitude:.3f}"
        cached = self._cache.get(key)
        if cached and datetime.now(timezone.utc) - cached.fetched_at < timedelta(seconds=self.settings.weather_cache_seconds):
            return cached
        if not self.settings.openweather_api_key:
            snapshot = _demo_weather(longitude, latitude, name, "OPENWEATHER_API_KEY is not configured")
            self._cache[key] = snapshot
            return snapshot
        try:
            response = await self.client.get(
                self.settings.openweather_current_url,
                params={"lat": latitude, "lon": longitude, "appid": self.settings.openweather_api_key, "units": "metric"},
                timeout=25.0,
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            weather = (payload.get("weather") or [{}])[0]
            main = payload.get("main") or {}
            wind = payload.get("wind") or {}
            clouds = payload.get("clouds") or {}
            rain = payload.get("rain") or {}
            system = payload.get("sys") or {}
            timestamp = datetime.fromtimestamp(float(payload.get("dt") or datetime.now(timezone.utc).timestamp()), tz=timezone.utc)
            sunrise = datetime.fromtimestamp(float(system.get("sunrise") or timestamp.replace(hour=5, minute=50).timestamp()), tz=timezone.utc)
            sunset = datetime.fromtimestamp(float(system.get("sunset") or timestamp.replace(hour=18, minute=27).timestamp()), tz=timezone.utc)
            direction = float(wind.get("deg") or 0.0)
            snapshot = WeatherSnapshot(
                mode="live",
                fetched_at=datetime.now(timezone.utc),
                location_name=str(payload.get("name") or name),
                longitude=float((payload.get("coord") or {}).get("lon", longitude)),
                latitude=float((payload.get("coord") or {}).get("lat", latitude)),
                temperature_c=float(main.get("temp", 0.0)),
                feels_like_c=float(main.get("feels_like", main.get("temp", 0.0))),
                humidity_percent=float(main.get("humidity", 0.0)),
                pressure_hpa=float(main.get("pressure", 0.0)),
                wind_speed_mps=float(wind.get("speed", 0.0)),
                wind_direction_deg=direction,
                wind_direction_cardinal=_wind_cardinal(direction),
                wind_gust_mps=float(wind["gust"]) if wind.get("gust") is not None else None,
                cloud_cover_percent=float(clouds.get("all", 0.0)),
                rain_1h_mm=float(rain.get("1h", 0.0)),
                visibility_km=round(float(payload.get("visibility", 0.0)) / 1000.0, 2) if payload.get("visibility") is not None else None,
                condition=str(weather.get("description") or weather.get("main") or "Not reported").title(),
                weather_code=int(weather.get("id") or 0),
                sunrise=sunrise,
                sunset=sunset,
                timezone_offset_seconds=int(payload.get("timezone") or 3600),
                is_daylight=sunrise <= timestamp <= sunset,
                note="Current weather observation from OpenWeather for the requested coordinate.",
            )
            self._cache[key] = snapshot
            return snapshot
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Weather request failed: %s", exc)
            snapshot = _demo_weather(longitude, latitude, name, f"the weather request failed ({type(exc).__name__})")
            self._cache[key] = snapshot
            return snapshot

    async def fetch_forecast(self, longitude: float, latitude: float, name: str = "Northern Gombe") -> WeatherForecastSnapshot:
        key = f"{longitude:.3f}:{latitude:.3f}"
        cached = self._forecast_cache.get(key)
        if cached and datetime.now(timezone.utc) - cached.fetched_at < timedelta(seconds=self.settings.weather_cache_seconds):
            return cached
        if not self.settings.openweather_api_key:
            forecast = _demo_forecast(longitude, latitude, name, "OPENWEATHER_API_KEY is not configured")
            self._forecast_cache[key] = forecast
            return forecast
        try:
            response = await self.client.get(
                self.settings.openweather_forecast_url,
                params={"lat": latitude, "lon": longitude, "appid": self.settings.openweather_api_key, "units": "metric"},
                timeout=30.0,
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            points: list[WeatherForecastPoint] = []
            for item in (payload.get("list") or [])[:24]:
                main = item.get("main") or {}
                wind = item.get("wind") or {}
                clouds = item.get("clouds") or {}
                rain = item.get("rain") or {}
                weather = (item.get("weather") or [{}])[0]
                direction = float(wind.get("deg") or 0.0)
                points.append(WeatherForecastPoint(
                    timestamp=datetime.fromtimestamp(float(item.get("dt") or 0), tz=timezone.utc),
                    temperature_c=float(main.get("temp", 0.0)),
                    feels_like_c=float(main.get("feels_like", main.get("temp", 0.0))),
                    humidity_percent=float(main.get("humidity", 0.0)),
                    pressure_hpa=float(main.get("pressure", 0.0)),
                    wind_speed_mps=float(wind.get("speed", 0.0)),
                    wind_direction_deg=direction,
                    wind_direction_cardinal=_wind_cardinal(direction),
                    cloud_cover_percent=float(clouds.get("all", 0.0)),
                    precipitation_probability=float(item.get("pop") or 0.0),
                    rain_3h_mm=float(rain.get("3h", 0.0)),
                    condition=str(weather.get("description") or weather.get("main") or "Not reported").title(),
                    weather_code=int(weather.get("id") or 0),
                ))
            city = payload.get("city") or {}
            forecast = WeatherForecastSnapshot(
                mode="live",
                fetched_at=datetime.now(timezone.utc),
                location_name=str(city.get("name") or name),
                longitude=float((city.get("coord") or {}).get("lon", longitude)),
                latitude=float((city.get("coord") or {}).get("lat", latitude)),
                points=points,
                note="OpenWeather five-day forecast in three-hour steps for the requested coordinate.",
            )
            self._forecast_cache[key] = forecast
            return forecast
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Weather forecast request failed: %s", exc)
            forecast = _demo_forecast(longitude, latitude, name, f"the forecast request failed ({type(exc).__name__})")
            self._forecast_cache[key] = forecast
            return forecast

    async def fetch_map_tile(self, layer: str, z: int, x: int, y: int) -> tuple[bytes, str]:
        if layer not in ALLOWED_WEATHER_LAYERS:
            raise ValueError("Unsupported weather map layer")
        if not self.settings.openweather_api_key:
            raise RuntimeError("OPENWEATHER_API_KEY is not configured")
        url = self.settings.openweather_tile_url.format(layer=layer, z=z, x=x, y=y)
        response = await self.client.get(url, params={"appid": self.settings.openweather_api_key}, timeout=25.0)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "image/png")
