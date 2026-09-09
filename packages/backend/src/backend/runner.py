"""Background job execution and persistence.

Long runs are executed off the request thread and polled, mirroring how the BioDT
grassland prototype digital twin offloads its simulations: a century-scale run
takes tens of seconds, far past a sensible HTTP timeout.

Jobs live in SQLite so a restart does not lose finished results. `JobStore` is a
deliberately small surface -- submit, get, results, list -- so swapping the
thread pool for Celery or a HPC queue later touches this file and nothing else.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from ecocore import run_simulation
from ecocore.units import DAYS_PER_YEAR

from .scenario import build_grid, build_weather, tile_recorder
from .schemas import JobStatus, ScenarioConfig

__all__ = ["JobStore"]

PROFILE_KEYS = ("stand_profile", "sward_profile", "dbh_histogram")
"""Recorded fields served separately from the numeric series, because they are
nested and large enough to dominate a results payload."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobStore:
    """SQLite-backed job registry with a thread-pool executor."""

    def __init__(self, database: str | Path = "simulations.db", max_workers: int = 2) -> None:
        self.database = str(database)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._connect().close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                state TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                simulated_days INTEGER NOT NULL DEFAULT 0,
                total_days INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                finished_at TEXT,
                error TEXT,
                scenario TEXT NOT NULL,
                results TEXT,
                profiles TEXT
            )
            """
        )
        connection.commit()
        return connection

    def _write(self, query: str, args: tuple) -> None:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(query, args)
                connection.commit()
            finally:
                connection.close()

    def _read(self, query: str, args: tuple = ()) -> list[sqlite3.Row]:
        connection = self._connect()
        try:
            return connection.execute(query, args).fetchall()
        finally:
            connection.close()

    # ------------------------------------------------------------ commands --

    def submit(self, config: ScenarioConfig) -> JobStatus:
        job_id = uuid.uuid4().hex[:12]
        total_days = config.years * DAYS_PER_YEAR
        self._write(
            "INSERT INTO jobs (id, name, state, total_days, created_at, scenario)"
            " VALUES (?, ?, 'queued', ?, ?, ?)",
            (job_id, config.name, total_days, _now(), config.model_dump_json()),
        )
        self._executor.submit(self._run, job_id, config)
        return self.status(job_id)

    def _run(self, job_id: str, config: ScenarioConfig) -> None:
        try:
            self._write("UPDATE jobs SET state='running' WHERE id=?", (job_id,))
            grid = build_grid(config)
            weather = build_weather(config)

            def progress(done: int, total: int) -> None:
                self._write(
                    "UPDATE jobs SET progress=?, simulated_days=? WHERE id=?",
                    (done / total if total else 1.0, done, job_id),
                )

            result = run_simulation(
                grid,
                weather,
                years=config.years,
                record_every=config.record_every_days,
                seed=config.seed,
                progress=progress,
                recorder=tile_recorder,
            )

            series, profiles = self._split(result)
            self._write(
                "UPDATE jobs SET state='done', progress=1.0, finished_at=?,"
                " results=?, profiles=? WHERE id=?",
                (_now(), json.dumps(series), json.dumps(profiles), job_id),
            )
        except Exception:
            self._write(
                "UPDATE jobs SET state='failed', finished_at=?, error=? WHERE id=?",
                (_now(), traceback.format_exc(limit=5), job_id),
            )

    @staticmethod
    def _split(result) -> tuple[dict, dict]:
        """Separate the numeric time series from the nested profile snapshots."""
        series_tiles = []
        profiles: dict[str, list[dict]] = {}
        for (x, y), records in result.tile_series.items():
            numeric = []
            nested = []
            for record in records:
                numeric.append({k: v for k, v in record.items() if k not in PROFILE_KEYS})
                nested.append({k: record.get(k) for k in PROFILE_KEYS if k in record})
            series_tiles.append({"x": x, "y": y, "series": numeric})
            profiles[f"{x},{y}"] = nested
        years = [d / DAYS_PER_YEAR for d in result.recorded_days]
        return (
            {"recorded_days": result.recorded_days, "years": years, "tiles": series_tiles},
            profiles,
        )

    # ------------------------------------------------------------- queries --

    def status(self, job_id: str) -> JobStatus | None:
        rows = self._read("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not rows:
            return None
        row = rows[0]
        return JobStatus(
            id=row["id"],
            name=row["name"],
            state=row["state"],
            progress=row["progress"],
            simulated_days=row["simulated_days"],
            total_days=row["total_days"],
            created_at=row["created_at"],
            finished_at=row["finished_at"],
            error=row["error"],
        )

    def results(self, job_id: str) -> dict | None:
        rows = self._read("SELECT scenario, results FROM jobs WHERE id=?", (job_id,))
        if not rows or rows[0]["results"] is None:
            return None
        payload = json.loads(rows[0]["results"])
        payload["id"] = job_id
        payload["scenario"] = json.loads(rows[0]["scenario"])
        return payload

    def profiles(self, job_id: str, x: int, y: int) -> list[dict] | None:
        rows = self._read("SELECT profiles FROM jobs WHERE id=?", (job_id,))
        if not rows or rows[0]["profiles"] is None:
            return None
        return json.loads(rows[0]["profiles"]).get(f"{x},{y}")

    def list_jobs(self, limit: int = 50) -> list[JobStatus]:
        rows = self._read(
            "SELECT id FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [self.status(row["id"]) for row in rows]

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
