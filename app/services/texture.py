from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    value = np.clip((x - edge0) / max(edge1 - edge0, 1e-9), 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def ndvi_to_texture(ndvi: np.ndarray, valid: np.ndarray, width: int = 960, height: int = 720) -> bytes:
    values = np.nan_to_num(ndvi.astype(np.float32), nan=-0.2)
    sand = np.array([183, 137, 78], dtype=np.float32)
    dry = np.array([150, 127, 74], dtype=np.float32)
    sparse = np.array([119, 133, 66], dtype=np.float32)
    grass = np.array([67, 125, 58], dtype=np.float32)
    dense = np.array([29, 91, 49], dtype=np.float32)

    rgb = np.empty((*values.shape, 3), dtype=np.float32)
    t1 = _smoothstep(-0.05, 0.16, values)[..., None]
    t2 = _smoothstep(0.14, 0.32, values)[..., None]
    t3 = _smoothstep(0.30, 0.58, values)[..., None]
    base = sand * (1 - t1) + dry * t1
    base = base * (1 - t2) + sparse * t2
    base = base * (1 - t3) + grass * t3
    t4 = _smoothstep(0.54, 0.78, values)[..., None]
    rgb[:] = base * (1 - t4) + dense * t4

    gy, gx = np.gradient(values)
    shade = np.clip(1.0 + (gx * -0.32 + gy * 0.24), 0.82, 1.18)[..., None]
    rgb *= shade
    alpha = np.where(valid, 220, 0).astype(np.uint8)
    rgba = np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), alpha])

    image = Image.fromarray(rgba, "RGBA").resize((width, height), Image.Resampling.BICUBIC)
    image = image.filter(ImageFilter.GaussianBlur(radius=0.7))
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def simulation_to_texture(
    vegetation: np.ndarray,
    desert: np.ndarray,
    barrier: np.ndarray,
    width: int = 960,
    height: int = 720,
) -> bytes:
    veg = np.clip(vegetation, 0.0, 1.0)
    des = np.clip(desert, 0.0, 1.0)
    bar = np.clip(barrier, 0.0, 1.0)

    sand = np.array([203, 133, 47], dtype=np.float32)
    soil = np.array([128, 82, 45], dtype=np.float32)
    green = np.array([50, 164, 80], dtype=np.float32)
    bright = np.array([104, 255, 150], dtype=np.float32)
    rgb = soil[None, None, :] * (1 - des[..., None]) + sand[None, None, :] * des[..., None]
    rgb = rgb * (1 - veg[..., None] * 0.72) + green[None, None, :] * (veg[..., None] * 0.72)
    rgb = rgb * (1 - bar[..., None] * 0.85) + bright[None, None, :] * (bar[..., None] * 0.85)
    alpha = np.clip(45 + 170 * np.maximum(des, veg * 0.65), 0, 220).astype(np.uint8)
    rgba = np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), alpha])

    image = Image.fromarray(rgba, "RGBA").resize((width, height), Image.Resampling.BILINEAR)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def make_social_preview() -> bytes:
    image = Image.new("RGB", (1200, 630), (5, 17, 18))
    draw = ImageDraw.Draw(image)
    for index in range(14):
        x = 40 + index * 84
        height = 180 + (index % 5) * 34
        draw.ellipse((x - 18, 480 - height, x + 18, 480 - height + 36), fill=(58, 170, 90))
        draw.rectangle((x - 5, 480 - height + 26, x + 5, 500), fill=(96, 72, 44))
    draw.rectangle((0, 500, 1200, 630), fill=(173, 117, 52))
    draw.text((62, 62), "NORTHERN GOMBE", fill=(113, 245, 181))
    draw.text((62, 106), "Desertification & Afforestation Twin", fill=(240, 248, 238))
    draw.text((62, 162), "Live NDVI • Cellular automata • Great Green Wall planning", fill=(185, 205, 193))
    output = BytesIO()
    image.save(output, format="JPEG", quality=91, optimize=True)
    return output.getvalue()


def mask_texture_to_features(
    texture_png: bytes,
    feature_collection: dict,
    bbox: tuple[float, float, float, float],
) -> bytes:
    """Apply an alpha mask so rectangular image sources only appear inside selected polygons."""
    image = Image.open(BytesIO(texture_png)).convert("RGBA")
    width, height = image.size
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    west, south, east, north = bbox

    def project(point: list[float]) -> tuple[float, float]:
        longitude, latitude = float(point[0]), float(point[1])
        x = (longitude - west) / max(east - west, 1e-9) * (width - 1)
        y = (north - latitude) / max(north - south, 1e-9) * (height - 1)
        return x, y

    for feature in feature_collection.get("features", []):
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        polygons = coordinates if geometry.get("type") == "MultiPolygon" else [coordinates]
        for polygon in polygons:
            if not polygon:
                continue
            exterior = [project(point) for point in polygon[0]]
            if len(exterior) >= 3:
                draw.polygon(exterior, fill=255)
            for hole in polygon[1:]:
                projected = [project(point) for point in hole]
                if len(projected) >= 3:
                    draw.polygon(projected, fill=0)

    original_alpha = image.getchannel("A")
    combined = Image.fromarray(
        np.minimum(np.asarray(original_alpha, dtype=np.uint8), np.asarray(mask, dtype=np.uint8)),
        mode="L",
    )
    image.putalpha(combined)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def array_to_rgba_png(array: np.ndarray) -> bytes:
    """Encode a uint8 RGBA array as PNG bytes."""
    image = Image.fromarray(array.astype(np.uint8), mode="RGBA")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
