from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.models import ExecutionRecord


class ToolingRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.database_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.init_schema()

    def init_schema(self) -> None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.executescript(
                """
                CREATE TABLE IF NOT EXISTS tools (
                    name TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    input_schema TEXT NOT NULL,
                    required_permissions TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_policies (
                    agent_id TEXT PRIMARY KEY,
                    policy_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS executions (
                    execution_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    output_json TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    duration_ms INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS execution_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    artifact_path TEXT,
                    artifact_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(execution_id) REFERENCES executions(execution_id)
                );
                """
            )
            self._conn.commit()

    def upsert_tool(
        self,
        *,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        required_permissions: list[str],
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO tools(name, description, input_schema, required_permissions, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description=excluded.description,
                    input_schema=excluded.input_schema,
                    required_permissions=excluded.required_permissions,
                    updated_at=excluded.updated_at
                """,
                (
                    name,
                    description,
                    json.dumps(input_schema),
                    json.dumps(required_permissions),
                    now,
                ),
            )
            self._conn.commit()

    def create_execution(
        self,
        *,
        execution_id: str,
        request_id: str,
        agent_id: str,
        tool_name: str,
        input_payload: dict[str, Any],
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO executions(
                    execution_id, request_id, agent_id, tool_name, status, input_json,
                    output_json, error_code, error_message, duration_ms, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    request_id,
                    agent_id,
                    tool_name,
                    "running",
                    json.dumps(input_payload),
                    None,
                    None,
                    None,
                    0,
                    now,
                    now,
                ),
            )
            self._conn.commit()

    def complete_execution(
        self,
        *,
        execution_id: str,
        status: str,
        output_payload: dict[str, Any],
        error_code: str | None,
        error_message: str | None,
        duration_ms: int,
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                UPDATE executions
                SET status=?, output_json=?, error_code=?, error_message=?, duration_ms=?, updated_at=?
                WHERE execution_id=?
                """,
                (
                    status,
                    json.dumps(output_payload),
                    error_code,
                    error_message,
                    duration_ms,
                    now,
                    execution_id,
                ),
            )
            self._conn.commit()

    def add_artifact(
        self,
        *,
        execution_id: str,
        artifact_type: str,
        artifact_path: str | None,
        artifact_json: dict[str, Any] | None,
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO execution_artifacts(
                    execution_id, artifact_type, artifact_path, artifact_json, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    artifact_type,
                    artifact_path,
                    json.dumps(artifact_json or {}),
                    now,
                ),
            )
            self._conn.commit()

    def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        with self._lock:
            cursor = self._conn.cursor()
            row = cursor.execute(
                "SELECT * FROM executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        if not row:
            return None
        return ExecutionRecord(
            execution_id=row["execution_id"],
            request_id=row["request_id"],
            agent_id=row["agent_id"],
            tool_name=row["tool_name"],
            status=row["status"],
            input_json=json.loads(row["input_json"] or "{}"),
            output_json=json.loads(row["output_json"] or "{}"),
            error_code=row["error_code"],
            error_message=row["error_message"],
            duration_ms=int(row["duration_ms"] or 0),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def health_check(self) -> bool:
        with self._lock:
            cursor = self._conn.cursor()
            row = cursor.execute("SELECT 1 AS ok").fetchone()
        return bool(row and row["ok"] == 1)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

