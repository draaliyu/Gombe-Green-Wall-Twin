from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TwinStore:
    """Small SQLite repository for field observations and restoration projects."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialise(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS field_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    observer TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    lga TEXT,
                    observation_type TEXT NOT NULL,
                    tree_count INTEGER,
                    survival_percent REAL,
                    species TEXT,
                    condition TEXT,
                    notes TEXT,
                    photo_url TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS restoration_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    name TEXT NOT NULL,
                    organisation TEXT,
                    lga TEXT,
                    status TEXT NOT NULL,
                    target_trees INTEGER,
                    planted_trees INTEGER,
                    species TEXT,
                    start_date TEXT,
                    funding_source TEXT,
                    manager TEXT,
                    geometry_json TEXT NOT NULL DEFAULT '{}',
                    notes TEXT
                );
                CREATE TABLE IF NOT EXISTS project_inspections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    inspected_at TEXT NOT NULL,
                    survival_percent REAL,
                    maintenance_score REAL,
                    grazing_damage INTEGER NOT NULL DEFAULT 0,
                    fire_damage INTEGER NOT NULL DEFAULT 0,
                    notes TEXT,
                    FOREIGN KEY(project_id) REFERENCES restoration_projects(id)
                );
                """
            )

    def list_observations(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM field_observations ORDER BY id DESC LIMIT ?", (max(1, min(limit, 1000)),)
            ).fetchall()
        return [self._row(row) for row in rows]

    def create_observation(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO field_observations (
                    created_at, observer, latitude, longitude, lga, observation_type,
                    tree_count, survival_percent, species, condition, notes, photo_url,
                    status, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    payload["observer"],
                    float(payload["latitude"]),
                    float(payload["longitude"]),
                    payload.get("lga"),
                    payload["observation_type"],
                    payload.get("tree_count"),
                    payload.get("survival_percent"),
                    payload.get("species"),
                    payload.get("condition"),
                    payload.get("notes"),
                    payload.get("photo_url"),
                    payload.get("status", "pending"),
                    json.dumps(payload.get("metadata") or {}),
                ),
            )
            row = connection.execute("SELECT * FROM field_observations WHERE id = ?", (cursor.lastrowid,)).fetchone()
        assert row is not None
        return self._row(row)

    def update_observation_status(self, observation_id: int, status: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            connection.execute("UPDATE field_observations SET status = ? WHERE id = ?", (status, observation_id))
            row = connection.execute("SELECT * FROM field_observations WHERE id = ?", (observation_id,)).fetchone()
        return self._row(row) if row else None

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM restoration_projects ORDER BY id DESC").fetchall()
            output = []
            for row in rows:
                project = self._row(row)
                inspections = connection.execute(
                    "SELECT * FROM project_inspections WHERE project_id = ? ORDER BY id DESC", (row["id"],)
                ).fetchall()
                project["inspections"] = [self._row(item) for item in inspections]
                output.append(project)
        return output

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO restoration_projects (
                    created_at, updated_at, name, organisation, lga, status,
                    target_trees, planted_trees, species, start_date,
                    funding_source, manager, geometry_json, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    now,
                    payload["name"],
                    payload.get("organisation"),
                    payload.get("lga"),
                    payload.get("status", "planned"),
                    payload.get("target_trees"),
                    payload.get("planted_trees"),
                    payload.get("species"),
                    payload.get("start_date"),
                    payload.get("funding_source"),
                    payload.get("manager"),
                    json.dumps(payload.get("geometry") or {}),
                    payload.get("notes"),
                ),
            )
            row = connection.execute("SELECT * FROM restoration_projects WHERE id = ?", (cursor.lastrowid,)).fetchone()
        assert row is not None
        return self._row(row)

    def add_inspection(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            exists = connection.execute("SELECT id FROM restoration_projects WHERE id = ?", (project_id,)).fetchone()
            if not exists:
                raise KeyError(project_id)
            cursor = connection.execute(
                """
                INSERT INTO project_inspections (
                    project_id, inspected_at, survival_percent, maintenance_score,
                    grazing_damage, fire_damage, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    payload.get("inspected_at") or datetime.now(timezone.utc).isoformat(),
                    payload.get("survival_percent"),
                    payload.get("maintenance_score"),
                    int(bool(payload.get("grazing_damage"))),
                    int(bool(payload.get("fire_damage"))),
                    payload.get("notes"),
                ),
            )
            connection.execute(
                "UPDATE restoration_projects SET updated_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), project_id),
            )
            row = connection.execute("SELECT * FROM project_inspections WHERE id = ?", (cursor.lastrowid,)).fetchone()
        assert row is not None
        return self._row(row)

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        output = dict(row)
        for key in ("metadata_json", "geometry_json"):
            if key in output:
                target = "metadata" if key == "metadata_json" else "geometry"
                try:
                    output[target] = json.loads(output.pop(key) or "{}")
                except json.JSONDecodeError:
                    output[target] = {}
        for key in ("grazing_damage", "fire_damage"):
            if key in output:
                output[key] = bool(output[key])
        return output
