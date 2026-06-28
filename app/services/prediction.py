from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.config import Settings


FEATURES = [
    "month_sin",
    "month_cos",
    "rain_mm",
    "ndvi_lag1",
    "ndvi_lag2",
    "desert_lag1",
    "vegetation_lag1",
]


class PredictionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path: Path = settings.model_path
        self.model: dict[str, Any] | None = None
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.model = None
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("features") == FEATURES:
                self.model = payload
        except (json.JSONDecodeError, OSError):
            self.model = None

    def train(self, temporal_points: list[dict[str, Any]], mode: str) -> dict[str, Any]:
        x, y = self._dataset(temporal_points)
        if len(y) < self.settings.prediction_min_samples:
            raise ValueError(
                f"At least {self.settings.prediction_min_samples} eligible monthly points are required; {len(y)} are available."
            )
        split = max(8, int(len(y) * 0.8))
        x_train, y_train = x[:split], y[:split]
        x_test, y_test = x[split:], y[split:]
        mean = x_train.mean(axis=0)
        std = x_train.std(axis=0)
        std[std < 1e-6] = 1.0
        z_train = (x_train - mean) / std
        design = np.column_stack([np.ones(len(z_train)), z_train])
        alpha = 0.8
        penalty = np.eye(design.shape[1]) * alpha
        penalty[0, 0] = 0.0
        weights = np.linalg.solve(design.T @ design + penalty, design.T @ y_train)
        if len(x_test):
            z_test = (x_test - mean) / std
            predictions = np.column_stack([np.ones(len(z_test)), z_test]) @ weights
            errors = predictions - y_test
            mae = float(np.mean(np.abs(errors)))
            rmse = float(np.sqrt(np.mean(errors**2)))
            denominator = float(np.sum((y_test - np.mean(y_test)) ** 2))
            r2 = 1.0 - float(np.sum(errors**2)) / denominator if denominator > 1e-8 else 0.0
        else:
            mae = rmse = r2 = 0.0
        coefficients = {name: round(float(weight), 6) for name, weight in zip(["intercept", *FEATURES], weights, strict=False)}
        self.model = {
            "version": 1,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "training_mode": mode,
            "features": FEATURES,
            "feature_mean": mean.tolist(),
            "feature_std": std.tolist(),
            "weights": weights.tolist(),
            "samples": int(len(y)),
            "train_samples": int(len(y_train)),
            "validation_samples": int(len(y_test)),
            "metrics": {"mae": round(mae, 5), "rmse": round(rmse, 5), "r2": round(r2, 5)},
            "coefficients": coefficients,
            "target": "next-month mean NDVI",
            "limitations": (
                "This compact ridge-regression model learns from the platform timeline. Derived or demonstration timeline points "
                "produce an experimental model and must not be presented as an operational land forecast."
            ),
        }
        self.path.write_text(json.dumps(self.model, indent=2), encoding="utf-8")
        return self.model

    def status(self) -> dict[str, Any]:
        return {
            "trained": self.model is not None,
            "model": self.model,
            "minimum_samples": self.settings.prediction_min_samples,
        }

    def forecast(self, temporal_points: list[dict[str, Any]], months: int = 6) -> dict[str, Any]:
        if self.model is None:
            return {
                "available": False,
                "reason": "No trained model is available. An administrator must retrain after sufficient timeline data exist.",
                "predictions": [],
            }
        points = [dict(item) for item in temporal_points]
        if len(points) < 3:
            return {"available": False, "reason": "At least three timeline points are required.", "predictions": []}
        mean = np.asarray(self.model["feature_mean"], dtype=np.float64)
        std = np.asarray(self.model["feature_std"], dtype=np.float64)
        weights = np.asarray(self.model["weights"], dtype=np.float64)
        predictions = []
        current_period = points[-1]["period"]
        year, month = map(int, current_period.split("-"))
        for _ in range(max(1, min(months, 24))):
            month += 1
            if month > 12:
                month = 1
                year += 1
            previous = points[-1]
            previous2 = points[-2]
            rain = self._seasonal_rain(points, month)
            vector = np.asarray([
                np.sin(month / 12 * np.pi * 2),
                np.cos(month / 12 * np.pi * 2),
                rain,
                float(previous["ndvi"]),
                float(previous2["ndvi"]),
                float(previous.get("desert_fraction") or 0.0),
                float(previous.get("vegetated_fraction") or 0.0),
            ], dtype=np.float64)
            z = (vector - mean) / std
            prediction = float((np.column_stack([np.ones(1), z.reshape(1, -1)]) @ weights).item())
            prediction = float(np.clip(prediction, -0.1, 0.85))
            uncertainty = float(max(self.model["metrics"].get("rmse", 0.04), 0.035) * (1.0 + len(predictions) * 0.14))
            item = {
                "period": f"{year:04d}-{month:02d}",
                "ndvi": round(prediction, 4),
                "lower": round(max(-0.1, prediction - 1.64 * uncertainty), 4),
                "upper": round(min(0.9, prediction + 1.64 * uncertainty), 4),
                "rain_mm_assumption": round(rain, 2),
                "mode": "model_prediction",
            }
            predictions.append(item)
            points.append({
                **item,
                "vegetated_fraction": float(np.clip((prediction + 0.05) / 0.72, 0, 1)),
                "desert_fraction": float(np.clip(0.72 - prediction, 0, 1)),
                "rain_mm": rain,
            })
        importance = self._importance()
        return {
            "available": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "training_mode": self.model["training_mode"],
            "target": self.model["target"],
            "predictions": predictions,
            "metrics": self.model["metrics"],
            "feature_importance": importance,
            "limitations": self.model["limitations"],
        }

    @staticmethod
    def _dataset(points: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
        features = []
        targets = []
        for index in range(2, len(points) - 1):
            current = points[index]
            previous = points[index - 1]
            previous2 = points[index - 2]
            try:
                month = int(str(current["period"])[5:7])
                features.append([
                    np.sin(month / 12 * np.pi * 2),
                    np.cos(month / 12 * np.pi * 2),
                    float(current.get("rain_mm") or 0.0),
                    float(previous["ndvi"]),
                    float(previous2["ndvi"]),
                    float(previous.get("desert_fraction") or 0.0),
                    float(previous.get("vegetated_fraction") or 0.0),
                ])
                targets.append(float(points[index + 1]["ndvi"]))
            except (KeyError, TypeError, ValueError):
                continue
        return np.asarray(features, dtype=np.float64), np.asarray(targets, dtype=np.float64)

    @staticmethod
    def _seasonal_rain(points: list[dict[str, Any]], month: int) -> float:
        candidates = [float(item.get("rain_mm") or 0.0) for item in points if int(str(item.get("period", "0000-00"))[5:7] or 0) == month]
        if candidates:
            return float(np.mean(candidates))
        return float(max(0.0, 75 + 85 * np.sin((month - 4) / 12 * np.pi * 2)))

    def _importance(self) -> list[dict[str, Any]]:
        assert self.model is not None
        weights = np.abs(np.asarray(self.model["weights"][1:], dtype=np.float64))
        total = float(np.sum(weights)) or 1.0
        pairs = sorted(zip(FEATURES, weights / total, strict=False), key=lambda item: item[1], reverse=True)
        return [{"feature": name, "importance": round(float(value), 4)} for name, value in pairs]
