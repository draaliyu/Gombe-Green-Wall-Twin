from __future__ import annotations

import asyncio
import math
from typing import Any

import httpx

from app.services.geometry import feature_name, geometry_centroid, normalize_name, slugify

GOMBE_LGA_NAMES = [
    "Akko",
    "Balanga",
    "Billiri",
    "Dukku",
    "Funakaye",
    "Gombe",
    "Kaltungo",
    "Kwami",
    "Nafada",
    "Shongom",
    "Yamaltu/Deba",
]

# The five LGAs in Gombe North senatorial district are used as the northern focus.
NORTHERN_LGA_NAMES = ["Dukku", "Funakaye", "Gombe", "Kwami", "Nafada"]

LGA_CENTRES: dict[str, tuple[float, float]] = {
    "Akko": (10.99, 10.13),
    "Balanga": (11.69, 9.91),
    "Billiri": (11.23, 9.86),
    "Dukku": (10.77, 10.82),
    "Funakaye": (11.43, 10.86),
    "Gombe": (11.17, 10.29),
    "Kaltungo": (11.31, 9.81),
    "Kwami": (11.02, 10.50),
    "Nafada": (11.33, 11.10),
    "Shongom": (11.17, 9.60),
    "Yamaltu/Deba": (11.56, 10.20),
}

FALLBACK_GOMBE = {
    "type": "FeatureCollection",
    "name": "Gombe State approximate fallback boundary",
    "features": [{
        "type": "Feature",
        "properties": {"shapeName": "Gombe", "name": "Gombe State", "source": "approximate fallback"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [10.37, 10.92], [10.55, 11.34], [10.92, 11.48], [11.28, 11.42],
                [11.67, 11.23], [11.97, 10.94], [12.16, 10.63], [12.23, 10.28],
                [12.03, 9.88], [11.72, 9.61], [11.38, 9.50], [11.04, 9.64],
                [10.79, 9.88], [10.49, 10.13], [10.30, 10.48], [10.37, 10.92],
            ]],
        },
    }],
}


def _hexagon(center: tuple[float, float], radius_lon: float, radius_lat: float) -> list[list[float]]:
    longitude, latitude = center
    points: list[list[float]] = []
    for index in range(6):
        angle = math.radians(30 + index * 60)
        points.append([
            round(longitude + math.cos(angle) * radius_lon, 6),
            round(latitude + math.sin(angle) * radius_lat, 6),
        ])
    points.append(points[0])
    return points


def fallback_lgas() -> dict[str, Any]:
    features = []
    sizes = {
        "Dukku": (0.34, 0.31), "Funakaye": (0.27, 0.25), "Nafada": (0.23, 0.22),
        "Kwami": (0.25, 0.22), "Gombe": (0.18, 0.17), "Akko": (0.28, 0.25),
        "Yamaltu/Deba": (0.27, 0.23), "Balanga": (0.29, 0.25), "Billiri": (0.20, 0.17),
        "Kaltungo": (0.19, 0.16), "Shongom": (0.22, 0.18),
    }
    northern = {normalize_name(name) for name in NORTHERN_LGA_NAMES}
    for name in GOMBE_LGA_NAMES:
        centre = LGA_CENTRES[name]
        radius_lon, radius_lat = sizes[name]
        features.append({
            "type": "Feature",
            "id": slugify(name),
            "properties": {
                "name": name,
                "shapeName": name,
                "slug": slugify(name),
                "northern_focus": normalize_name(name) in northern,
                "source": "approximate fallback geometry",
            },
            "geometry": {"type": "Polygon", "coordinates": [_hexagon(centre, radius_lon, radius_lat)]},
        })
    return {"type": "FeatureCollection", "name": "Gombe LGAs fallback", "features": features}


def _prepare_lgas(collection: dict[str, Any]) -> dict[str, Any]:
    aliases = {normalize_name(name): name for name in GOMBE_LGA_NAMES}
    aliases["yamaltudeba"] = "Yamaltu/Deba"
    aliases["yamaltudeba"] = "Yamaltu/Deba"
    aliases["shomgom"] = "Shongom"
    northern = {normalize_name(name) for name in NORTHERN_LGA_NAMES}
    features: list[dict[str, Any]] = []
    found: set[str] = set()
    for raw_feature in collection.get("features", []):
        raw_name = feature_name(raw_feature)
        key = normalize_name(raw_name)
        canonical = aliases.get(key)
        if not canonical:
            continue
        feature = dict(raw_feature)
        properties = dict(feature.get("properties") or {})
        properties.update({
            "name": canonical,
            "shapeName": canonical,
            "slug": slugify(canonical),
            "northern_focus": normalize_name(canonical) in northern,
            "source": "geoBoundaries gbOpen ADM2 (GRID3)",
        })
        centroid = geometry_centroid(feature.get("geometry"))
        properties["centroid_lon"] = round(centroid[0], 6)
        properties["centroid_lat"] = round(centroid[1], 6)
        feature["id"] = slugify(canonical)
        feature["properties"] = properties
        features.append(feature)
        found.add(canonical)
    if len(found) != len(GOMBE_LGA_NAMES):
        return fallback_lgas()
    features.sort(key=lambda item: item["properties"]["name"])
    return {"type": "FeatureCollection", "name": "Gombe State Local Government Areas", "features": features}


async def _fetch_collection(client: httpx.AsyncClient, level: str) -> dict[str, Any]:
    metadata = await client.get(
        f"https://www.geoboundaries.org/api/current/gbOpen/NGA/{level}/",
        timeout=10.0,
    )
    metadata.raise_for_status()
    payload = metadata.json()
    download_url = payload.get("simplifiedGeometryGeoJSON") or payload.get("gjDownloadURL")
    if not download_url:
        raise ValueError(f"No {level} boundary URL returned")
    response = await client.get(download_url, timeout=35.0, follow_redirects=True)
    response.raise_for_status()
    return response.json()


async def fetch_gombe_boundaries(client: httpx.AsyncClient) -> tuple[dict[str, Any], dict[str, Any]]:
    state = FALLBACK_GOMBE
    lgas = fallback_lgas()
    adm1_result, adm2_result = await asyncio.gather(
        _fetch_collection(client, "ADM1"),
        _fetch_collection(client, "ADM2"),
        return_exceptions=True,
    )
    if isinstance(adm1_result, dict):
        matches = []
        for feature in adm1_result.get("features", []):
            values = [str(value).lower() for value in (feature.get("properties") or {}).values()]
            if any("gombe" in value for value in values):
                prepared = dict(feature)
                properties = dict(prepared.get("properties") or {})
                properties.update({"name": "Gombe State", "shapeName": "Gombe", "source": "geoBoundaries gbOpen ADM1"})
                prepared["properties"] = properties
                matches.append(prepared)
        if matches:
            state = {"type": "FeatureCollection", "name": "Gombe State", "features": matches}
    if isinstance(adm2_result, dict):
        lgas = _prepare_lgas(adm2_result)
    return state, lgas


def northern_lgas(collection: dict[str, Any]) -> dict[str, Any]:
    features = [feature for feature in collection.get("features", []) if (feature.get("properties") or {}).get("northern_focus")]
    return {"type": "FeatureCollection", "name": "Northern Gombe focus LGAs", "features": features}


def location_points(collection: dict[str, Any]) -> dict[str, Any]:
    features = []
    for feature in collection.get("features", []):
        properties = feature.get("properties") or {}
        longitude = properties.get("centroid_lon")
        latitude = properties.get("centroid_lat")
        if longitude is None or latitude is None:
            longitude, latitude = geometry_centroid(feature.get("geometry"))
        features.append({
            "type": "Feature",
            "id": properties.get("slug"),
            "properties": {
                "name": properties.get("name") or feature_name(feature),
                "slug": properties.get("slug"),
                "kind": "northern LGA" if properties.get("northern_focus") else "Gombe LGA",
                "northern_focus": bool(properties.get("northern_focus")),
            },
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
        })
    return {"type": "FeatureCollection", "name": "Gombe LGA centres", "features": features}


def bbox_polygon(bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    west, south, east, north = bbox
    return {
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    }
