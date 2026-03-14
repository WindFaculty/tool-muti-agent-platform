from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.models import (
    AgentMessageRecord,
    DeploymentRecord,
    EvaluationRecord,
    ExecutionRecord,
    KnowledgeDocumentRecord,
    MemoryEntryRecord,
    ProjectRecord,
    PromptTemplateRecord,
    RunStepRecord,
    TaskRecord,
    TaskRunRecord,
    WorkflowDefinitionRecord,
)


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

                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    default_workflow_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description_md TEXT NOT NULL,
                    requirements_md TEXT NOT NULL,
                    expected_output_md TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    task_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );

                CREATE TABLE IF NOT EXISTS task_runs (
                    run_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_step_id TEXT,
                    result_summary TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );

                CREATE TABLE IF NOT EXISTS run_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    input_json TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, step_id),
                    FOREIGN KEY(run_id) REFERENCES task_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS agent_messages (
                    message_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    step_id TEXT,
                    agent_id TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    content_md TEXT NOT NULL,
                    artifacts_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES task_runs(run_id),
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
                );

                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    document_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content_path TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    summary_md TEXT NOT NULL,
                    source TEXT NOT NULL,
                    indexed_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );

                CREATE TABLE IF NOT EXISTS memory_entries (
                    entry_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content_path TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    source_run_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );

                CREATE TABLE IF NOT EXISTS workflow_definitions (
                    workflow_id TEXT PRIMARY KEY,
                    version TEXT NOT NULL,
                    description TEXT NOT NULL,
                    steps_yaml TEXT NOT NULL,
                    is_builtin INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS prompt_templates (
                    prompt_name TEXT PRIMARY KEY,
                    role_name TEXT NOT NULL,
                    template_body TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evaluations (
                    run_id TEXT PRIMARY KEY,
                    score REAL NOT NULL,
                    metrics_json TEXT NOT NULL,
                    summary_md TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES task_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS deployments (
                    deployment_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    run_id TEXT,
                    target TEXT NOT NULL,
                    status TEXT NOT NULL,
                    log_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
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
                    self._dump_json(input_schema),
                    self._dump_json(required_permissions),
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
                    self._dump_json(input_payload),
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
                    self._dump_json(output_payload),
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
                    self._dump_json(artifact_json or {}),
                    now,
                ),
            )
            self._conn.commit()

    def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        row = self._fetchone("SELECT * FROM executions WHERE execution_id = ?", (execution_id,))
        if not row:
            return None
        return ExecutionRecord(
            execution_id=row["execution_id"],
            request_id=row["request_id"],
            agent_id=row["agent_id"],
            tool_name=row["tool_name"],
            status=row["status"],
            input_json=self._load_json(row["input_json"]),
            output_json=self._load_json(row["output_json"]),
            error_code=row["error_code"],
            error_message=row["error_message"],
            duration_ms=int(row["duration_ms"] or 0),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def upsert_project(
        self,
        *,
        project_id: str,
        name: str,
        root_path: str,
        default_workflow_id: str,
        status: str,
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO projects(
                    project_id, name, root_path, default_workflow_id, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    name=excluded.name,
                    root_path=excluded.root_path,
                    default_workflow_id=excluded.default_workflow_id,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (project_id, name, root_path, default_workflow_id, status, now, now),
            )
            self._conn.commit()

    def get_project(self, project_id: str) -> ProjectRecord | None:
        row = self._fetchone("SELECT * FROM projects WHERE project_id = ?", (project_id,))
        if not row:
            return None
        return ProjectRecord(**dict(row))

    def list_projects(self) -> list[ProjectRecord]:
        rows = self._fetchall("SELECT * FROM projects ORDER BY created_at DESC")
        return [ProjectRecord(**dict(row)) for row in rows]

    def create_task(
        self,
        *,
        task_id: str,
        project_id: str,
        title: str,
        description_md: str,
        requirements_md: str,
        expected_output_md: str,
        priority: str,
        workflow_id: str,
        status: str,
        task_path: str,
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO tasks(
                    task_id, project_id, title, description_md, requirements_md,
                    expected_output_md, priority, workflow_id, status, task_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    project_id,
                    title,
                    description_md,
                    requirements_md,
                    expected_output_md,
                    priority,
                    workflow_id,
                    status,
                    task_path,
                    now,
                    now,
                ),
            )
            self._conn.commit()

    def update_task_status(self, task_id: str, status: str) -> None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                (status, self._now_iso(), task_id),
            )
            self._conn.commit()

    def get_task(self, task_id: str) -> TaskRecord | None:
        row = self._fetchone("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        if not row:
            return None
        return TaskRecord(**dict(row))

    def list_tasks(self, project_id: str | None = None) -> list[TaskRecord]:
        if project_id:
            rows = self._fetchall(
                "SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
        else:
            rows = self._fetchall("SELECT * FROM tasks ORDER BY created_at DESC")
        return [TaskRecord(**dict(row)) for row in rows]

    def create_task_run(
        self,
        *,
        run_id: str,
        task_id: str,
        project_id: str,
        workflow_id: str,
        status: str,
        current_step_id: str | None = None,
        result_summary: str | None = None,
        started_at: str | None = None,
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO task_runs(
                    run_id, task_id, project_id, workflow_id, status, current_step_id,
                    result_summary, started_at, ended_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    task_id,
                    project_id,
                    workflow_id,
                    status,
                    current_step_id,
                    result_summary,
                    started_at or now,
                    None,
                    now,
                    now,
                ),
            )
            self._conn.commit()

    def update_task_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        current_step_id: str | None = None,
        result_summary: str | None = None,
        ended_at: str | None = None,
    ) -> None:
        assignments: list[str] = []
        params: list[Any] = []
        if status is not None:
            assignments.append("status = ?")
            params.append(status)
        if current_step_id is not None:
            assignments.append("current_step_id = ?")
            params.append(current_step_id)
        if result_summary is not None:
            assignments.append("result_summary = ?")
            params.append(result_summary)
        if ended_at is not None:
            assignments.append("ended_at = ?")
            params.append(ended_at)
        assignments.append("updated_at = ?")
        params.append(self._now_iso())
        params.append(run_id)
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                f"UPDATE task_runs SET {', '.join(assignments)} WHERE run_id = ?",
                tuple(params),
            )
            self._conn.commit()

    def get_task_run(self, run_id: str) -> TaskRunRecord | None:
        row = self._fetchone("SELECT * FROM task_runs WHERE run_id = ?", (run_id,))
        if not row:
            return None
        return TaskRunRecord(**dict(row))

    def list_task_runs(self, task_id: str | None = None) -> list[TaskRunRecord]:
        if task_id:
            rows = self._fetchall(
                "SELECT * FROM task_runs WHERE task_id = ? ORDER BY created_at DESC",
                (task_id,),
            )
        else:
            rows = self._fetchall("SELECT * FROM task_runs ORDER BY created_at DESC")
        return [TaskRunRecord(**dict(row)) for row in rows]

    def upsert_run_step(
        self,
        *,
        run_id: str,
        step_id: str,
        agent_id: str,
        status: str,
        retry_count: int,
        input_json: dict[str, Any],
        output_json: dict[str, Any],
        started_at: str | None = None,
        ended_at: str | None = None,
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO run_steps(
                    run_id, step_id, agent_id, status, retry_count, input_json, output_json,
                    started_at, ended_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, step_id) DO UPDATE SET
                    agent_id=excluded.agent_id,
                    status=excluded.status,
                    retry_count=excluded.retry_count,
                    input_json=excluded.input_json,
                    output_json=excluded.output_json,
                    started_at=excluded.started_at,
                    ended_at=excluded.ended_at,
                    updated_at=excluded.updated_at
                """,
                (
                    run_id,
                    step_id,
                    agent_id,
                    status,
                    retry_count,
                    self._dump_json(input_json),
                    self._dump_json(output_json),
                    started_at,
                    ended_at,
                    now,
                ),
            )
            self._conn.commit()

    def list_run_steps(self, run_id: str) -> list[RunStepRecord]:
        rows = self._fetchall("SELECT * FROM run_steps WHERE run_id = ? ORDER BY id ASC", (run_id,))
        return [
            RunStepRecord(
                run_id=row["run_id"],
                step_id=row["step_id"],
                agent_id=row["agent_id"],
                status=row["status"],
                retry_count=int(row["retry_count"] or 0),
                input_json=self._load_json(row["input_json"]),
                output_json=self._load_json(row["output_json"]),
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def add_agent_message(
        self,
        *,
        message_id: str,
        run_id: str,
        task_id: str,
        step_id: str | None,
        agent_id: str,
        message_type: str,
        content_md: str,
        artifacts_json: list[dict[str, Any]],
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO agent_messages(
                    message_id, run_id, task_id, step_id, agent_id, message_type,
                    content_md, artifacts_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    run_id,
                    task_id,
                    step_id,
                    agent_id,
                    message_type,
                    content_md,
                    self._dump_json(artifacts_json),
                    now,
                ),
            )
            self._conn.commit()

    def list_agent_messages(self, run_id: str) -> list[AgentMessageRecord]:
        rows = self._fetchall(
            "SELECT * FROM agent_messages WHERE run_id = ? ORDER BY created_at ASC",
            (run_id,),
        )
        return [
            AgentMessageRecord(
                message_id=row["message_id"],
                run_id=row["run_id"],
                task_id=row["task_id"],
                step_id=row["step_id"],
                agent_id=row["agent_id"],
                message_type=row["message_type"],
                content_md=row["content_md"],
                artifacts_json=self._load_json(row["artifacts_json"], default=[]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def upsert_knowledge_document(
        self,
        *,
        document_id: str,
        project_id: str,
        title: str,
        content_path: str,
        content_sha256: str,
        tags_json: list[str],
        summary_md: str,
        source: str,
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO knowledge_documents(
                    document_id, project_id, title, content_path, content_sha256,
                    tags_json, summary_md, source, indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    title=excluded.title,
                    content_path=excluded.content_path,
                    content_sha256=excluded.content_sha256,
                    tags_json=excluded.tags_json,
                    summary_md=excluded.summary_md,
                    source=excluded.source,
                    indexed_at=excluded.indexed_at
                """,
                (
                    document_id,
                    project_id,
                    title,
                    content_path,
                    content_sha256,
                    self._dump_json(tags_json),
                    summary_md,
                    source,
                    now,
                ),
            )
            self._conn.commit()

    def list_knowledge_documents(self, project_id: str) -> list[KnowledgeDocumentRecord]:
        rows = self._fetchall(
            "SELECT * FROM knowledge_documents WHERE project_id = ? ORDER BY indexed_at DESC",
            (project_id,),
        )
        return [
            KnowledgeDocumentRecord(
                document_id=row["document_id"],
                project_id=row["project_id"],
                title=row["title"],
                content_path=row["content_path"],
                content_sha256=row["content_sha256"],
                tags_json=self._load_json(row["tags_json"], default=[]),
                summary_md=row["summary_md"],
                source=row["source"],
                indexed_at=row["indexed_at"],
            )
            for row in rows
        ]

    def upsert_memory_entry(
        self,
        *,
        entry_id: str,
        project_id: str,
        kind: str,
        title: str,
        content_path: str,
        content_sha256: str,
        tags_json: list[str],
        embedding_json: list[float],
        source_run_id: str | None,
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO memory_entries(
                    entry_id, project_id, kind, title, content_path, content_sha256,
                    tags_json, embedding_json, source_run_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entry_id) DO UPDATE SET
                    kind=excluded.kind,
                    title=excluded.title,
                    content_path=excluded.content_path,
                    content_sha256=excluded.content_sha256,
                    tags_json=excluded.tags_json,
                    embedding_json=excluded.embedding_json,
                    source_run_id=excluded.source_run_id
                """,
                (
                    entry_id,
                    project_id,
                    kind,
                    title,
                    content_path,
                    content_sha256,
                    self._dump_json(tags_json),
                    self._dump_json(embedding_json),
                    source_run_id,
                    now,
                ),
            )
            self._conn.commit()

    def list_memory_entries(self, project_id: str) -> list[MemoryEntryRecord]:
        rows = self._fetchall(
            "SELECT * FROM memory_entries WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        )
        return [
            MemoryEntryRecord(
                entry_id=row["entry_id"],
                project_id=row["project_id"],
                kind=row["kind"],
                title=row["title"],
                content_path=row["content_path"],
                content_sha256=row["content_sha256"],
                tags_json=self._load_json(row["tags_json"], default=[]),
                embedding_json=self._load_json(row["embedding_json"], default=[]),
                source_run_id=row["source_run_id"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def upsert_workflow_definition(
        self,
        *,
        workflow_id: str,
        version: str,
        description: str,
        steps_yaml: str,
        is_builtin: bool,
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO workflow_definitions(
                    workflow_id, version, description, steps_yaml, is_builtin, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    version=excluded.version,
                    description=excluded.description,
                    steps_yaml=excluded.steps_yaml,
                    is_builtin=excluded.is_builtin,
                    updated_at=excluded.updated_at
                """,
                (workflow_id, version, description, steps_yaml, int(is_builtin), now),
            )
            self._conn.commit()

    def get_workflow_definition(self, workflow_id: str) -> WorkflowDefinitionRecord | None:
        row = self._fetchone(
            "SELECT * FROM workflow_definitions WHERE workflow_id = ?",
            (workflow_id,),
        )
        if not row:
            return None
        return WorkflowDefinitionRecord(
            workflow_id=row["workflow_id"],
            version=row["version"],
            description=row["description"],
            steps_yaml=row["steps_yaml"],
            is_builtin=bool(row["is_builtin"]),
            updated_at=row["updated_at"],
        )

    def list_workflow_definitions(self) -> list[WorkflowDefinitionRecord]:
        rows = self._fetchall("SELECT * FROM workflow_definitions ORDER BY workflow_id ASC")
        return [
            WorkflowDefinitionRecord(
                workflow_id=row["workflow_id"],
                version=row["version"],
                description=row["description"],
                steps_yaml=row["steps_yaml"],
                is_builtin=bool(row["is_builtin"]),
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def upsert_prompt_template(
        self,
        *,
        prompt_name: str,
        role_name: str,
        template_body: str,
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO prompt_templates(prompt_name, role_name, template_body, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(prompt_name) DO UPDATE SET
                    role_name=excluded.role_name,
                    template_body=excluded.template_body,
                    updated_at=excluded.updated_at
                """,
                (prompt_name, role_name, template_body, now),
            )
            self._conn.commit()

    def get_prompt_template(self, prompt_name: str) -> PromptTemplateRecord | None:
        row = self._fetchone(
            "SELECT * FROM prompt_templates WHERE prompt_name = ?",
            (prompt_name,),
        )
        if not row:
            return None
        return PromptTemplateRecord(**dict(row))

    def list_prompt_templates(self) -> list[PromptTemplateRecord]:
        rows = self._fetchall("SELECT * FROM prompt_templates ORDER BY prompt_name ASC")
        return [PromptTemplateRecord(**dict(row)) for row in rows]

    def upsert_evaluation(
        self,
        *,
        run_id: str,
        score: float,
        metrics_json: dict[str, Any],
        summary_md: str,
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO evaluations(run_id, score, metrics_json, summary_md, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    score=excluded.score,
                    metrics_json=excluded.metrics_json,
                    summary_md=excluded.summary_md,
                    updated_at=excluded.updated_at
                """,
                (run_id, score, self._dump_json(metrics_json), summary_md, now, now),
            )
            self._conn.commit()

    def get_evaluation(self, run_id: str) -> EvaluationRecord | None:
        row = self._fetchone("SELECT * FROM evaluations WHERE run_id = ?", (run_id,))
        if not row:
            return None
        return EvaluationRecord(
            run_id=row["run_id"],
            score=float(row["score"]),
            metrics_json=self._load_json(row["metrics_json"]),
            summary_md=row["summary_md"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_deployment(
        self,
        *,
        deployment_id: str,
        project_id: str,
        run_id: str | None,
        target: str,
        status: str,
        log_path: str | None,
    ) -> None:
        now = self._now_iso()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO deployments(
                    deployment_id, project_id, run_id, target, status, log_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (deployment_id, project_id, run_id, target, status, log_path, now, now),
            )
            self._conn.commit()

    def get_deployment(self, deployment_id: str) -> DeploymentRecord | None:
        row = self._fetchone("SELECT * FROM deployments WHERE deployment_id = ?", (deployment_id,))
        if not row:
            return None
        return DeploymentRecord(**dict(row))

    def get_monitoring_summary(self) -> dict[str, Any]:
        rows = self._fetchall("SELECT status, COUNT(*) AS total FROM task_runs GROUP BY status")
        return {
            "projects": self._scalar("SELECT COUNT(*) FROM projects"),
            "tasks": self._scalar("SELECT COUNT(*) FROM tasks"),
            "runs": self._scalar("SELECT COUNT(*) FROM task_runs"),
            "executions": self._scalar("SELECT COUNT(*) FROM executions"),
            "run_statuses": {row["status"]: int(row["total"]) for row in rows},
        }

    def health_check(self) -> bool:
        row = self._fetchone("SELECT 1 AS ok")
        return bool(row and row["ok"] == 1)

    def _fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            cursor = self._conn.cursor()
            return cursor.execute(sql, params).fetchone()

    def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            cursor = self._conn.cursor()
            return cursor.execute(sql, params).fetchall()

    def _scalar(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        row = self._fetchone(sql, params)
        if not row:
            return 0
        return int(row[0] or 0)

    @staticmethod
    def _dump_json(value: Any) -> str:
        return json.dumps(value)

    @staticmethod
    def _load_json(value: str | None, default: Any = None) -> Any:
        if not value:
            return {} if default is None else default
        return json.loads(value)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
