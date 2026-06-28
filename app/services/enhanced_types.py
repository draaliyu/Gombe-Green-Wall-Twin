from __future__ import annotations

from typing import Any


def normalise_external_landcover(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    if isinstance(payload.get("classes"), dict):
        return payload
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("classes"), dict):
        return data
    return None
