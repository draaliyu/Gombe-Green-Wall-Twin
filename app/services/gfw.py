from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings
from app.models import GFWSnapshot, GFWYearLoss

LOGGER = logging.getLogger("green-wall-twin.gfw")


class GFWService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client

    def demo_snapshot(self, note: str | None = None) -> GFWSnapshot:
        now = datetime.now(timezone.utc)
        # Demonstration values are deterministic and deliberately modest; never presented as observations.
        years = [GFWYearLoss(year=year, area_ha=value) for year, value in [
            (2020, 12.0), (2021, 18.5), (2022, 14.2), (2023, 21.0), (2024, 17.8),
        ]]
        return GFWSnapshot(
            mode="demo",
            fetched_at=now,
            dataset=self.settings.gfw_dataset,
            dataset_version=self.settings.gfw_dataset_version,
            years=years,
            cumulative_loss_ha=round(sum(item.area_ha for item in years), 2),
            latest_year_loss_ha=years[-1].area_ha,
            note=note or "GFW API key is not configured; labelled demonstration forest-change values are active.",
        )

    async def fetch(self, geometry: dict[str, Any]) -> GFWSnapshot:
        if not self.settings.has_gfw_credentials:
            return self.demo_snapshot()
        current_year = datetime.now(timezone.utc).year
        start_year = max(2001, current_year - 8)
        sql = (
            "SELECT umd_tree_cover_loss__year AS year, SUM(area__ha) AS area_ha "
            "FROM results "
            f"WHERE umd_tree_cover_loss__year >= {start_year} "
            "GROUP BY umd_tree_cover_loss__year ORDER BY year"
        )
        url = (
            "https://data-api.globalforestwatch.org/dataset/"
            f"{self.settings.gfw_dataset}/{self.settings.gfw_dataset_version}/query/json"
        )
        try:
            response = await self.client.post(
                url,
                json={"sql": sql, "geometry": geometry},
                headers={
                    "x-api-key": self.settings.gfw_api_key,
                    "Content-Type": "application/json",
                    **({"Origin": self.settings.gfw_origin} if self.settings.gfw_origin else {}),
                },
                timeout=60.0,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
            raw_rows = payload.get("data") or []
            years: list[GFWYearLoss] = []
            for row in raw_rows:
                year = int(row.get("year") or row.get("umd_tree_cover_loss__year") or 0)
                area = float(row.get("area_ha") or row.get("sum") or 0.0)
                if year > 0:
                    years.append(GFWYearLoss(year=year, area_ha=round(area, 3)))
            now = datetime.now(timezone.utc)
            return GFWSnapshot(
                mode="live",
                fetched_at=now,
                dataset=self.settings.gfw_dataset,
                dataset_version=self.settings.gfw_dataset_version,
                years=years,
                cumulative_loss_ha=round(sum(item.area_ha for item in years), 3),
                latest_year_loss_ha=years[-1].area_ha if years else 0.0,
                note=(
                    "Tree-cover loss is a historical forest-change indicator from Global Forest Watch. "
                    "It does not by itself identify desertification, land-use cause, or restoration failure."
                ),
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("GFW refresh failed: %s", exc)
            return self.demo_snapshot(f"GFW request failed ({type(exc).__name__}); demonstration values are active.")
