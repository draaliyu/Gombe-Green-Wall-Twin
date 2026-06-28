from __future__ import annotations

import math
import re
from typing import Any, Iterable


def normalize_name(value: object) -> str:
    text = str(value or "").lower().replace("/", " ").replace("-", " ")
    return re.sub(r"[^a-z0-9]+", "", text)


def iter_polygons(geometry: dict[str, Any] | None) -> Iterable[list[list[float]]]:
    if not geometry:
        return
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if geometry_type == "Polygon":
        if coordinates:
            yield coordinates
    elif geometry_type == "MultiPolygon":
        for polygon in coordinates:
            if polygon:
                yield polygon


def iter_points(geometry: dict[str, Any] | None) -> Iterable[tuple[float, float]]:
    for polygon in iter_polygons(geometry):
        for ring in polygon:
            for point in ring:
                if len(point) >= 2:
                    yield float(point[0]), float(point[1])


def collection_bounds(collection: dict[str, Any]) -> tuple[float, float, float, float]:
    points: list[tuple[float, float]] = []
    for feature in collection.get("features", []):
        points.extend(iter_points(feature.get("geometry")))
    if not points:
        return 10.25, 9.45, 12.30, 11.70
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def geometry_centroid(geometry: dict[str, Any] | None) -> tuple[float, float]:
    points = list(iter_points(geometry))
    if not points:
        return 11.17, 10.29
    return sum(point[0] for point in points) / len(points), sum(point[1] for point in points) / len(points)


def point_in_ring(longitude: float, latitude: float, ring: list[list[float]]) -> bool:
    inside = False
    if len(ring) < 3:
        return False
    j = len(ring) - 1
    for i, point in enumerate(ring):
        xi, yi = float(point[0]), float(point[1])
        xj, yj = float(ring[j][0]), float(ring[j][1])
        intersects = ((yi > latitude) != (yj > latitude)) and (
            longitude < (xj - xi) * (latitude - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def point_in_geometry(longitude: float, latitude: float, geometry: dict[str, Any] | None) -> bool:
    for polygon in iter_polygons(geometry):
        if not polygon or not point_in_ring(longitude, latitude, polygon[0]):
            continue
        if any(point_in_ring(longitude, latitude, hole) for hole in polygon[1:]):
            continue
        return True
    return False


def feature_name(feature: dict[str, Any]) -> str:
    properties = feature.get("properties") or {}
    for key in ("name", "shapeName", "ADM2_EN", "admin2Name", "lga_name", "LGAName"):
        if properties.get(key):
            return str(properties[key])
    return "Unnamed area"


def slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text or "area"


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    radius = 6371.0088
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(value)))
