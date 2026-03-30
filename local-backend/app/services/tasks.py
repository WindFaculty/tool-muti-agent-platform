from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any
import unicodedata

from app.core.config import Settings
from app.core.ids import make_id
from app.core.time import add_month, combine_date_time, daterange, iso_date, iso_datetime, now_local, parse_date, parse_datetime
from app.db.repository import SQLiteRepository
from app.models.enums import RepeatRule, TaskPriority, TaskStatus
from app.models.schemas import CompleteTaskRequest, RescheduleTaskRequest, TaskCreateRequest, TaskRecord, TaskUpdateRequest


class TaskService:
    def __init__(self, repository: SQLiteRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def create_task(self, request: TaskCreateRequest) -> TaskRecord:
        now = now_local()
        normalized = self._normalize_payload(request.model_dump(), existing=None)
        normalized.update(
            {
                "id": make_id("task"),
                "created_at": iso_datetime(now),
                "updated_at": iso_datetime(now),
                "completed_at": None,
            }
        )
        self._repository.create_task(normalized)
        self.sync_task_artifacts(normalized)
        return TaskRecord.model_validate(self._repository.get_task(normalized["id"]))

    def update_task(self, task_id: str, request: TaskUpdateRequest) -> TaskRecord:
        existing = self._require_task(task_id)
        updates = request.model_dump(exclude_unset=True)
        if not updates:
            return TaskRecord.model_validate(existing)
        merged = {**existing, **updates}
        normalized = self._normalize_payload(merged, existing=existing)
        normalized["updated_at"] = iso_datetime(now_local())
        self._repository.update_task(task_id, normalized)
        refreshed = self._require_task(task_id)
        self.sync_task_artifacts(refreshed)
        return TaskRecord.model_validate(refreshed)

    def complete_task(self, task_id: str, request: CompleteTaskRequest) -> TaskRecord:
        existing = self._require_task(task_id)
        completed_at = request.completed_at or iso_datetime(now_local())
        merged = {
            **existing,
            "status": TaskStatus.DONE.value,
            "completed_at": completed_at,
            "updated_at": iso_datetime(now_local()),
        }
        normalized = self._normalize_payload(merged, existing=existing)
        normalized["completed_at"] = completed_at
        normalized["status"] = TaskStatus.DONE.value
        self._repository.update_task(task_id, normalized)
        refreshed = self._require_task(task_id)
        self.sync_task_artifacts(refreshed)
        return TaskRecord.model_validate(refreshed)

    def reschedule_task(self, task_id: str, request: RescheduleTaskRequest) -> TaskRecord:
        existing = self._require_task(task_id)
        merged = {**existing, **request.model_dump(exclude_unset=True)}
        normalized = self._normalize_payload(merged, existing=existing)
        normalized["updated_at"] = iso_datetime(now_local())
        if normalized["status"] == TaskStatus.INBOX.value and normalized["scheduled_date"]:
            normalized["status"] = TaskStatus.PLANNED.value
        self._repository.update_task(task_id, normalized)
        refreshed = self._require_task(task_id)
        self.sync_task_artifacts(refreshed)
        return TaskRecord.model_validate(refreshed)

    def list_day(self, target_date: date) -> dict[str, Any]:
        day_iso = iso_date(target_date)
        items = self._sort_items(
            self._repository.list_tasks(
                "status NOT IN ('done', 'cancelled') AND scheduled_date = ?",
                (day_iso,),
            )
            + self._repository.list_occurrences_between(day_iso, day_iso)
        )
        overdue = self.list_overdue()["items"]
        due_soon = self._due_soon_items(items, target_date)
        in_progress = [item for item in items if item["status"] == TaskStatus.IN_PROGRESS.value]
        return {
            "date": day_iso,
            "items": items,
            "overdue": overdue,
            "due_soon": due_soon,
            "in_progress": in_progress,
        }

    def list_week(self, start_date: date) -> dict[str, Any]:
        end_date = start_date + timedelta(days=6)
        start_iso = iso_date(start_date)
        end_iso = iso_date(end_date)
        items = self._sort_items(
            self._repository.list_tasks(
                "status NOT IN ('done', 'cancelled') AND scheduled_date BETWEEN ? AND ?",
                (start_iso, end_iso),
            )
            + self._repository.list_occurrences_between(start_iso, end_iso)
        )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            grouped[item["scheduled_date"]].append(item)
        days = []
        for current in daterange(start_date, end_date):
            current_iso = iso_date(current)
            day_items = grouped.get(current_iso, [])
            days.append(
                {
                    "date": current_iso,
                    "task_count": len(day_items),
                    "high_priority_count": len(
                        [
                            item
                            for item in day_items
                            if item["priority"] in (TaskPriority.HIGH.value, TaskPriority.CRITICAL.value)
                        ]
                    ),
                    "items": day_items,
                }
            )
        return {
            "start_date": start_iso,
            "end_date": end_iso,
            "days": days,
            "overdue_count": len(self.list_overdue()["items"]),
            "conflicts": self.detect_conflicts(items),
        }

    def list_overdue(self) -> dict[str, Any]:
        now = now_local()
        items = []
        for item in self._repository.list_active_tasks():
            due_at = parse_datetime(item["due_at"])
            if due_at and due_at < now:
                items.append(item)
        return {"generated_at": iso_datetime(now), "items": self._sort_items(items)}

    def list_inbox(self, limit: int = 50) -> dict[str, Any]:
        items = self._repository.list_tasks("status = 'inbox'", ())[:limit]
        return {"items": items, "count": len(items)}

    def list_completed(self, limit: int = 50) -> dict[str, Any]:
        items = self._repository.list_tasks("status = 'done'", ())[:limit]
        return {"items": items, "count": len(items)}

    def list_active_tasks(self) -> list[dict[str, Any]]:
        return self._repository.list_active_tasks()

    def get_task(self, task_id: str) -> TaskRecord:
        return TaskRecord.model_validate(self._require_task(task_id))

    def search_task(self, query: str) -> dict[str, Any] | None:
        needle = self._search_key(query)
        if not needle:
            return None
        tasks = self._repository.list_active_tasks()
        exact = next((task for task in tasks if self._search_key(task["title"]) == needle), None)
        if exact:
            return exact
        contains = [task for task in tasks if needle in self._search_key(task["title"])]
        return contains[0] if contains else None

    def sync_task_artifacts(self, task: dict[str, Any]) -> None:
        self._repository.replace_occurrences(task["id"], self._build_occurrences(task))
        self._repository.replace_reminders(task["id"], self._build_reminders(task))

    def detect_conflicts(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            if item.get("start_at") and item.get("end_at"):
                grouped[item["scheduled_date"]].append(item)

        conflicts: list[dict[str, Any]] = []
        for day, day_items in grouped.items():
            ordered = sorted(day_items, key=lambda value: value["start_at"] or "")
            for index in range(len(ordered) - 1):
                left = ordered[index]
                right = ordered[index + 1]
                left_end = parse_datetime(left["end_at"])
                right_start = parse_datetime(right["start_at"])
                if left_end and right_start and right_start < left_end:
                    conflicts.append(
                        {
                            "date": day,
                            "task_ids": [left["id"], right["id"]],
                            "titles": [left["title"], right["title"]],
                        }
                    )
        return conflicts

    def _require_task(self, task_id: str) -> dict[str, Any]:
        task = self._repository.get_task(task_id)
        if task is None:
            raise LookupError(f"Task '{task_id}' not found")
        return task

    def _normalize_payload(self, payload: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
        data = dict(payload)
        data["title"] = (data.get("title") or "").strip()
        if not data["title"]:
            raise ValueError("Task title must not be empty")

        start_at = parse_datetime(data.get("start_at"))
        end_at = parse_datetime(data.get("end_at"))
        due_at = parse_datetime(data.get("due_at"))
        scheduled_date = parse_date(data.get("scheduled_date"))

        is_all_day = bool(data.get("is_all_day"))
        if is_all_day:
            start_at = None
            end_at = None

        if start_at and end_at and end_at <= start_at:
            raise ValueError("end_at must be after start_at")

        if scheduled_date is None and start_at:
            scheduled_date = start_at.date()
        if scheduled_date is None and due_at:
            scheduled_date = due_at.date()
        if scheduled_date is None and data.get("status") == TaskStatus.PLANNED.value:
            data["status"] = TaskStatus.INBOX.value
        if scheduled_date and data.get("status") == TaskStatus.INBOX.value:
            data["status"] = TaskStatus.PLANNED.value
        if data.get("status") == TaskStatus.DONE.value and not data.get("completed_at"):
            data["completed_at"] = iso_datetime(now_local())

        data["scheduled_date"] = iso_date(scheduled_date)
        data["start_at"] = iso_datetime(start_at)
        data["end_at"] = iso_datetime(end_at)
        data["due_at"] = iso_datetime(due_at)
        data["is_all_day"] = is_all_day
        data["repeat_rule"] = self._normalize_repeat_rule(data.get("repeat_rule"))
        data["tags"] = [tag.strip() for tag in data.get("tags", []) if tag and tag.strip()]
        if existing is not None:
            data["created_at"] = existing["created_at"]
            data["id"] = existing["id"]
        return data

    def _normalize_repeat_rule(self, value: str | None) -> str:
        if value is None:
            return RepeatRule.NONE.value
        return RepeatRule(value).value

    def _sort_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        priority_rank = {
            TaskPriority.CRITICAL.value: 0,
            TaskPriority.HIGH.value: 1,
            TaskPriority.MEDIUM.value: 2,
            TaskPriority.LOW.value: 3,
        }
        return sorted(
            items,
            key=lambda item: (
                item.get("scheduled_date") or "",
                item.get("start_at") or item.get("due_at") or "",
                priority_rank.get(item.get("priority"), 9),
                item.get("title") or "",
            ),
        )

    def _due_soon_items(self, items: list[dict[str, Any]], target_date: date) -> list[dict[str, Any]]:
        if target_date != now_local().date():
            return []
        now = now_local()
        upper = now + timedelta(hours=self._settings.due_soon_window_hours)
        due_soon: list[dict[str, Any]] = []
        for item in items:
            candidate = parse_datetime(item.get("start_at")) or parse_datetime(item.get("due_at"))
            if candidate and now <= candidate <= upper:
                due_soon.append(item)
        return due_soon

    def _build_occurrences(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        rule = task.get("repeat_rule", RepeatRule.NONE.value)
        if rule == RepeatRule.NONE.value:
            return []
        base_date = parse_date(task.get("scheduled_date"))
        if base_date is None:
            start_at = parse_datetime(task.get("start_at"))
            due_at = parse_datetime(task.get("due_at"))
            base_date = (start_at or due_at or now_local()).date()

        start_time = parse_datetime(task.get("start_at"))
        end_time = parse_datetime(task.get("end_at"))
        due_time = parse_datetime(task.get("due_at"))
        created_at = iso_datetime(now_local())
        current = base_date
        items: list[dict[str, Any]] = []
        for _ in range(self._settings.occurrence_horizon_days):
            current = self._next_occurrence_date(current, rule)
            if current is None:
                break
            items.append(
                {
                    "id": make_id("occ"),
                    "task_id": task["id"],
                    "occurrence_date": iso_date(current),
                    "start_at": iso_datetime(combine_date_time(current, start_time.time()) if start_time else None),
                    "end_at": iso_datetime(combine_date_time(current, end_time.time()) if end_time else None),
                    "due_at": iso_datetime(combine_date_time(current, due_time.time()) if due_time else None),
                    "created_at": created_at,
                }
            )
        return items

    def _next_occurrence_date(self, current: date, rule: str) -> date | None:
        if rule == RepeatRule.DAILY.value:
            return current + timedelta(days=1)
        if rule == RepeatRule.WEEKDAYS.value:
            next_day = current + timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            return next_day
        if rule == RepeatRule.WEEKLY.value:
            return current + timedelta(days=7)
        if rule == RepeatRule.MONTHLY.value:
            return add_month(current)
        return None

    def _build_reminders(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        if task.get("status") in (TaskStatus.DONE.value, TaskStatus.CANCELLED.value):
            return []
        anchor = parse_datetime(task.get("start_at")) or parse_datetime(task.get("due_at"))
        if anchor is None:
            return []
        remind_at = anchor - timedelta(minutes=self._settings.reminder_lead_minutes)
        return [
            {
                "id": make_id("rem"),
                "task_id": task["id"],
                "remind_at": iso_datetime(remind_at),
                "delivered_at": None,
                "status": "pending",
                "created_at": iso_datetime(now_local()),
            }
        ]

    def _search_key(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value.casefold())
        return "".join(ch for ch in normalized if not unicodedata.combining(ch)).strip()
