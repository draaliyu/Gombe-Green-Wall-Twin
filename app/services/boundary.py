from __future__ import annotations

from typing import Any

import httpx

FALLBACK_GOMBE = {
    "type": "FeatureCollection",
    "name": "Gombe State approximate fallback boundary",
    "features": [{
        "type": "Feature",
        "properties": {"shapeName": "Gombe", "source": "approximate fallback"},
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

NORTHERN_REFERENCE_LOCATIONS = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature", "properties": {"name": "Dukku", "kind": "reference town"}, "geometry": {"type": "Point", "coordinates": [10.7722, 10.8238]}},
        {"type": "Feature", "properties": {"name": "Bajoga", "kind": "reference town"}, "geometry": {"type": "Point", "coordinates": [11.4322, 10.8534]}},
        {"type": "Feature", "properties": {"name": "Nafada", "kind": "reference town"}, "geometry": {"type": "Point", "coordinates": [11.3328, 11.0957]}},
        {"type": "Feature", "properties": {"name": "Kwami", "kind": "reference town"}, "geometry": {"type": "Point", "coordinates": [11.0155, 10.4948]}},
        {"type": "Feature", "properties": {"name": "Gombe", "kind": "state capital reference"}, "geometry": {"type": "Point", "coordinates": [11.1673, 10.2897]}},
        {"type": "Feature", "properties": {"name": "Mallam Sidi", "kind": "reference town"}, "geometry": {"type": "Point", "coordinates": [11.1748, 10.7364]}},
    ],
}


async def fetch_gombe_boundary(client: httpx.AsyncClient) -> dict[str, Any]:
    try:
        metadata = await client.get(
            "https://www.geoboundaries.org/api/current/gbOpen/NGA/ADM1/",
            timeout=20.0,
        )
        metadata.raise_for_status()
        download_url = metadata.json().get("simplifiedGeometryGeoJSON") or metadata.json().get("gjDownloadURL")
        if not download_url:
            raise ValueError("No boundary URL returned")
        response = await client.get(download_url, timeout=45.0, follow_redirects=True)
        response.raise_for_status()
        collection = response.json()
        matches = []
        for feature in collection.get("features", []):
            values = [str(value).lower() for value in (feature.get("properties") or {}).values()]
            if any("gombe" in value for value in values):
                matches.append(feature)
        if matches:
            for feature in matches:
                feature.setdefault("properties", {})["source"] = "geoBoundaries gbOpen ADM1"
            return {"type": "FeatureCollection", "name": "Gombe State", "features": matches}
    except Exception:  # noqa: BLE001
        pass
    return FALLBACK_GOMBE


def bbox_polygon(bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    west, south, east, north = bbox
    return {
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    }
