from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from app.core.time import iso_date, iso_datetime, now_local, parse_date
from app.models.enums import AnimationHint, AssistantEmotion, TaskPriority, TaskStatus
from app.models.schemas import (
    ChatCard,
    CompleteTaskRequest,
    RescheduleTaskRequest,
    TaskActionReport,
    TaskCreateRequest,
    TaskUpdateRequest,
)
from app.services.planner import PlannerService
from app.services.tasks import TaskService


@dataclass
class IntentResult:
    kind: str
    title: str | None = None
    date_value: date | None = None
    start_at: str | None = None
    due_at: str | None = None
    repeat_rule: str = "none"
    priority: str | None = None
    cards: list[ChatCard] = field(default_factory=list)


@dataclass
class ValidatedTurn:
    kind: str
    reply_text: str
    emotion: AssistantEmotion
    animation_hint: AnimationHint
    task_actions: list[TaskActionReport]
    cards: list[ChatCard]
    factual_context: dict[str, Any]


class ActionValidator:
    def __init__(self, task_service: TaskService, planner_service: PlannerService) -> None:
        self._task_service = task_service
        self._planner_service = planner_service

    def analyze(self, message: str, selected_date: str | None, notes_context: str | None = None) -> IntentResult:
        lowered = self._sanitize(message)
        if self._looks_like_create(lowered):
            return self._parse_create(lowered)
        if self._looks_like_complete(lowered):
            return self._parse_complete(lowered)
        if self._looks_like_reschedule(lowered):
            return self._parse_reschedule(lowered)
        if self._looks_like_priority(lowered):
            return self._parse_priority(lowered)
        if self._looks_like_planning(lowered, notes_context):
            return IntentResult(kind="planning", date_value=self._extract_date(lowered, selected_date))
        if any(token in lowered for token in ("qua han", "overdue")):
            return IntentResult(kind="lookup_overdue")
        if any(token in lowered for token in ("gap nhat", "urgent", "quan trong nhat")):
            return IntentResult(kind="lookup_urgency")
        if any(token in lowered for token in ("ranh luc nao", "free when", "free time")):
            return IntentResult(kind="lookup_free_time", date_value=self._extract_date(lowered, selected_date))
        if any(token in lowered for token in ("tuan nay", "this week", "7 ngay", "tong ket tuan")):
            return IntentResult(kind="lookup_week", date_value=self._extract_date(lowered, selected_date))
        if any(token in lowered for token in ("hom nay", "today", "ngay mai", "tomorrow")):
            return IntentResult(kind="lookup_day", date_value=self._extract_date(lowered, selected_date))
        return IntentResult(kind="lookup_day", date_value=self._extract_date(lowered, selected_date))

    def execute(self, intent: IntentResult) -> ValidatedTurn:
        actions: list[TaskActionReport] = []
        cards = list(intent.cards)

        if intent.kind == "lookup_day":
            summary = self._planner_service.daily_summary(intent.date_value or now_local().date())
            cards.append(ChatCard(type="today_summary", payload=summary))
            return ValidatedTurn(
                kind=intent.kind,
                reply_text=summary["text"],
                emotion=AssistantEmotion.SERIOUS,
                animation_hint=AnimationHint.EXPLAIN,
                task_actions=actions,
                cards=cards,
                factual_context={"summary": summary},
            )

        if intent.kind == "lookup_week":
            summary = self._planner_service.weekly_summary(intent.date_value or now_local().date())
            cards.append(ChatCard(type="week_summary", payload=summary))
            return ValidatedTurn(
                kind=intent.kind,
                reply_text=summary["text"],
                emotion=AssistantEmotion.SERIOUS,
                animation_hint=AnimationHint.EXPLAIN,
                task_actions=actions,
                cards=cards,
                factual_context={"summary": summary},
            )

        if intent.kind == "lookup_overdue":
            summary = self._planner_service.overdue_summary()
            cards.append(ChatCard(type="overdue_summary", payload=summary))
            return ValidatedTurn(
                kind=intent.kind,
                reply_text=summary["text"],
                emotion=AssistantEmotion.WARNING,
                animation_hint=AnimationHint.ALERT,
                task_actions=actions,
                cards=cards,
                factual_context={"summary": summary},
            )

        if intent.kind == "lookup_free_time":
            summary = self._planner_service.free_slots(intent.date_value or now_local().date())
            cards.append(ChatCard(type="free_time", payload=summary))
            return ValidatedTurn(
                kind=intent.kind,
                reply_text=summary["text"],
                emotion=AssistantEmotion.NEUTRAL,
                animation_hint=AnimationHint.EXPLAIN,
                task_actions=actions,
                cards=cards,
                factual_context={"summary": summary},
            )

        if intent.kind == "lookup_urgency":
            summary = self._planner_service.urgency_summary()
            cards.append(ChatCard(type="urgency_summary", payload=summary))
            return ValidatedTurn(
                kind=intent.kind,
                reply_text=summary["text"],
                emotion=AssistantEmotion.SERIOUS,
                animation_hint=AnimationHint.EXPLAIN,
                task_actions=actions,
                cards=cards,
                factual_context={"summary": summary},
            )

        if intent.kind == "planning":
            day = intent.date_value or now_local().date()
            daily = self._planner_service.daily_summary(day)
            weekly = self._planner_service.weekly_summary(day)
            cards.append(ChatCard(type="planning_context", payload={"daily": daily, "weekly": weekly}))
            return ValidatedTurn(
                kind=intent.kind,
                reply_text=daily["text"],
                emotion=AssistantEmotion.THINKING,
                animation_hint=AnimationHint.THINK,
                task_actions=actions,
                cards=cards,
                factual_context={"daily": daily, "weekly": weekly, "tasks": self._task_service.list_active_tasks()},
            )

        if intent.kind == "create_task":
            task = self._task_service.create_task(
                TaskCreateRequest(
                    title=intent.title or "Viec moi",
                    status=TaskStatus.PLANNED if intent.date_value else TaskStatus.INBOX,
                    priority=intent.priority or TaskPriority.MEDIUM.value,
                    scheduled_date=iso_date(intent.date_value),
                    start_at=intent.start_at,
                    due_at=intent.due_at,
                    repeat_rule=intent.repeat_rule,
                )
            )
            actions.append(
                TaskActionReport(
                    type="create_task",
                    status="applied",
                    task_id=task.id,
                    title=task.title,
                    detail="Task created from validated action",
                )
            )
            cards.append(ChatCard(type="task_action", payload={"task": task.model_dump()}))
            reply = f"Da tao viec '{task.title}'"
            reply += f" cho ngay {task.scheduled_date}." if task.scheduled_date else " vao Inbox."
            return ValidatedTurn(
                kind=intent.kind,
                reply_text=reply,
                emotion=AssistantEmotion.HAPPY,
                animation_hint=AnimationHint.CONFIRM,
                task_actions=actions,
                cards=cards,
                factual_context={"task": task.model_dump()},
            )

        if intent.kind == "complete_task":
            task = self._match_task_or_fail(intent.title)
            updated = self._task_service.complete_task(
                task["id"],
                CompleteTaskRequest(completed_at=iso_datetime(now_local())),
            )
            actions.append(
                TaskActionReport(
                    type="complete_task",
                    status="applied",
                    task_id=updated.id,
                    title=updated.title,
                )
            )
            cards.append(ChatCard(type="task_action", payload={"task": updated.model_dump()}))
            return ValidatedTurn(
                kind=intent.kind,
                reply_text=f"Da danh dau xong viec '{updated.title}'.",
                emotion=AssistantEmotion.HAPPY,
                animation_hint=AnimationHint.CONFIRM,
                task_actions=actions,
                cards=cards,
                factual_context={"task": updated.model_dump()},
            )

        if intent.kind == "reschedule_task":
            task = self._match_task_or_fail(intent.title)
            updated = self._task_service.reschedule_task(
                task["id"],
                RescheduleTaskRequest(
                    scheduled_date=iso_date(intent.date_value),
                    start_at=intent.start_at,
                ),
            )
            actions.append(
                TaskActionReport(
                    type="reschedule_task",
                    status="applied",
                    task_id=updated.id,
                    title=updated.title,
                )
            )
            cards.append(ChatCard(type="task_action", payload={"task": updated.model_dump()}))
            return ValidatedTurn(
                kind=intent.kind,
                reply_text=f"Da doi '{updated.title}' sang {updated.scheduled_date}.",
                emotion=AssistantEmotion.HAPPY,
                animation_hint=AnimationHint.CONFIRM,
                task_actions=actions,
                cards=cards,
                factual_context={"task": updated.model_dump()},
            )

        if intent.kind == "priority_task":
            task = self._match_task_or_fail(intent.title)
            updated = self._task_service.update_task(
                task["id"],
                TaskUpdateRequest(priority=intent.priority),
            )
            actions.append(
                TaskActionReport(
                    type="priority_task",
                    status="applied",
                    task_id=updated.id,
                    title=updated.title,
                )
            )
            cards.append(ChatCard(type="task_action", payload={"task": updated.model_dump()}))
            return ValidatedTurn(
                kind=intent.kind,
                reply_text=f"Da tang uu tien cho '{updated.title}' len muc {updated.priority}.",
                emotion=AssistantEmotion.HAPPY,
                animation_hint=AnimationHint.CONFIRM,
                task_actions=actions,
                cards=cards,
                factual_context={"task": updated.model_dump()},
            )

        summary = self._planner_service.daily_summary(now_local().date())
        cards.append(ChatCard(type="today_summary", payload=summary))
        return ValidatedTurn(
            kind="lookup_day",
            reply_text=summary["text"],
            emotion=AssistantEmotion.NEUTRAL,
            animation_hint=AnimationHint.EXPLAIN,
            task_actions=actions,
            cards=cards,
            factual_context={"summary": summary},
        )

    def _looks_like_create(self, text: str) -> bool:
        return any(text.startswith(prefix) for prefix in ("them", "tao", "nhac toi", "add ", "create "))

    def _looks_like_complete(self, text: str) -> bool:
        return any(token in text for token in ("danh dau", "xong", "hoan thanh", "complete"))

    def _looks_like_reschedule(self, text: str) -> bool:
        return any(token in text for token in ("doi", "chuyen", "move", "reschedule"))

    def _looks_like_priority(self, text: str) -> bool:
        return "uu tien" in text or "priority" in text

    def _looks_like_planning(self, text: str, notes_context: str | None) -> bool:
        planning_keywords = ("lap ke hoach", "phan tich", "tong hop", "chien luoc", "toi uu", "sap xep", "chia viec")
        return any(token in text for token in planning_keywords) or bool(notes_context and len(notes_context.split()) > 80)

    def _parse_create(self, text: str) -> IntentResult:
        title = self._extract_title(
            text,
            prefixes=("them task", "them viec", "them", "tao task", "tao viec", "tao", "nhac toi", "add task", "add", "create task", "create"),
        )
        target_date = self._extract_date(text, None, default_to_today=False)
        start_at = self._extract_datetime(text, target_date)
        repeat_rule = self._extract_repeat_rule(text)
        priority = self._extract_priority(text)
        due_at = start_at if "deadline" in text or "nop" in text else None
        return IntentResult(
            kind="create_task",
            title=title,
            date_value=target_date,
            start_at=iso_datetime(start_at) if start_at else None,
            due_at=iso_datetime(due_at) if due_at else None,
            repeat_rule=repeat_rule,
            priority=priority,
        )

    def _parse_complete(self, text: str) -> IntentResult:
        title = self._extract_title(
            text,
            prefixes=("danh dau", "hoan thanh", "complete", "xong"),
            stops=("la xong", "la done", "hoan thanh"),
        )
        return IntentResult(kind="complete_task", title=title)

    def _parse_reschedule(self, text: str) -> IntentResult:
        title_match = re.search(r"(?:doi|chuyen|move|reschedule)\s+(.*?)\s+(?:sang|to)\s+", text)
        title = title_match.group(1).strip() if title_match else self._extract_title(
            text,
            prefixes=("doi", "chuyen", "move", "reschedule"),
        )
        target_date = self._extract_date(text, None, default_to_today=False)
        start_at = self._extract_datetime(text, target_date)
        return IntentResult(
            kind="reschedule_task",
            title=title,
            date_value=target_date,
            start_at=iso_datetime(start_at) if start_at else None,
        )

    def _parse_priority(self, text: str) -> IntentResult:
        title_match = re.search(r"(?:tang uu tien|priority)\s+(.*?)\s+(?:len|to)\s+", text)
        title = title_match.group(1).strip() if title_match else self._extract_title(
            text,
            prefixes=("tang uu tien", "priority"),
        )
        return IntentResult(
            kind="priority_task",
            title=title,
            priority=self._extract_priority(text) or TaskPriority.HIGH.value,
        )

    def _extract_title(
        self,
        text: str,
        *,
        prefixes: tuple[str, ...],
        stops: tuple[str, ...] = ("luc", "vao", "sang", "to", "ngay", "mai", "hom nay", "thu"),
    ) -> str:
        cleaned = text
        for prefix in prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip()
                break
        for stop in stops:
            match = re.search(rf"\s+{re.escape(stop)}(?:\s+|$)", cleaned)
            if match:
                return cleaned[: match.start()].strip(" .")
        return cleaned.strip(" .")

    def _extract_priority(self, text: str) -> str | None:
        mapping = {
            "critical": TaskPriority.CRITICAL.value,
            "khan cap": TaskPriority.CRITICAL.value,
            "cao": TaskPriority.HIGH.value,
            "high": TaskPriority.HIGH.value,
            "trung binh": TaskPriority.MEDIUM.value,
            "medium": TaskPriority.MEDIUM.value,
            "thap": TaskPriority.LOW.value,
            "low": TaskPriority.LOW.value,
        }
        for key, value in mapping.items():
            if key in text:
                return value
        return None

    def _extract_repeat_rule(self, text: str) -> str:
        if "moi toi" in text or "moi ngay" in text or "daily" in text:
            return "daily"
        if "ngay trong tuan" in text or "weekdays" in text:
            return "weekdays"
        if "moi tuan" in text or "weekly" in text:
            return "weekly"
        if "moi thang" in text or "monthly" in text:
            return "monthly"
        return "none"

    def _extract_date(self, text: str, selected_date: str | None, *, default_to_today: bool = True) -> date | None:
        today = now_local().date()
        if "ngay mai" in text or re.search(r"\bmai\b", text) or "tomorrow" in text:
            return today + timedelta(days=1)
        if "hom nay" in text or "today" in text:
            return today

        weekdays = {
            "thu hai": 0,
            "thu ba": 1,
            "thu tu": 2,
            "thu nam": 3,
            "thu sau": 4,
            "thu bay": 5,
            "chu nhat": 6,
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        for label, weekday in weekdays.items():
            if label in text:
                delta = (weekday - today.weekday()) % 7
                delta = 7 if delta == 0 else delta
                return today + timedelta(days=delta)

        iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
        if iso_match:
            return date.fromisoformat(iso_match.group(1))
        if selected_date:
            return parse_date(selected_date) or today
        return today if default_to_today else None

    def _extract_datetime(self, text: str, target_date: date | None) -> datetime | None:
        if target_date is None:
            target_date = now_local().date()
        hour = None
        minute = 0
        match = re.search(r"(\d{1,2})(?::(\d{2}))?", text)
        if match:
            hour = int(match.group(1))
            if match.group(2):
                minute = int(match.group(2))
        elif "chieu" in text:
            hour = 15
        elif "toi" in text:
            hour = 19
        elif "sang" in text:
            hour = 9

        if hour is None:
            return None
        if ("chieu" in text or "pm" in text or "toi" in text) and hour < 12:
            hour += 12
        return datetime.combine(target_date, datetime.min.time()).replace(hour=hour, minute=minute)

    def _sanitize(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
        plain = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return " ".join(plain.replace("?", " ").replace("!", " ").split())

    def _match_task_or_fail(self, title: str | None) -> dict[str, Any]:
        task = self._task_service.search_task(title or "")
        if task is None:
            raise LookupError(f"Could not find task matching '{title}'")
        return task
