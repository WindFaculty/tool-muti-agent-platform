from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings


class PromptContextBuilderService:
    _TASK_FIELDS = (
        "title",
        "status",
        "priority",
        "scheduled_date",
        "start_at",
        "due_at",
        "repeat_rule",
    )
    _TASK_GROUP_FIELDS = (
        "items",
        "overdue",
        "due_soon",
    )
    _COUNT_FIELDS = (
        "task_count",
        "high_priority_count",
        "overdue_count",
        "due_soon_count",
        "deadline_count",
        "repeat_count",
        "count",
    )

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build_fast_prompt(
        self,
        *,
        user_message: str,
        intent: str,
        factual_context: dict[str, Any],
        spoken_brief: str | None,
    ) -> str:
        return json.dumps(
            self.build_fast_payload(
                user_message=user_message,
                intent=intent,
                factual_context=factual_context,
                spoken_brief=spoken_brief,
            ),
            ensure_ascii=False,
        )

    def build_plan_prompt(
        self,
        *,
        user_message: str,
        intent: str,
        selected_date: str | None,
        notes_context: str | None,
        factual_context: dict[str, Any],
        rolling_summary: str,
        long_term_memory: list[dict[str, Any]],
    ) -> str:
        return json.dumps(
            self.build_plan_payload(
                user_message=user_message,
                intent=intent,
                selected_date=selected_date,
                notes_context=notes_context,
                factual_context=factual_context,
                rolling_summary=rolling_summary,
                long_term_memory=long_term_memory,
            ),
            ensure_ascii=False,
        )

    def build_fast_payload(
        self,
        *,
        user_message: str,
        intent: str,
        factual_context: dict[str, Any],
        spoken_brief: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "msg": self._clean_text(user_message, word_limit=24),
            "intent": intent,
            "facts": self._build_fast_facts_block(factual_context),
        }
        brief = self._clean_text(spoken_brief, word_limit=18)
        if brief:
            payload["brief"] = brief
        return payload

    def build_plan_payload(
        self,
        *,
        user_message: str,
        intent: str,
        selected_date: str | None,
        notes_context: str | None,
        factual_context: dict[str, Any],
        rolling_summary: str,
        long_term_memory: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "msg": self._clean_text(user_message, word_limit=40),
            "intent": intent,
            "facts": self._compact_deep_facts(
                factual_context,
                task_limit=self._settings.deep_context_task_limit,
            ),
            "roll": self._join_lines(
                rolling_summary,
                line_limit=self._settings.rolling_summary_line_limit,
                word_limit=18,
            ),
            "mem": self._compact_memory(long_term_memory),
        }
        if selected_date:
            payload["date"] = selected_date
        notes_excerpt = self._clean_text(
            notes_context,
            word_limit=min(self._settings.notes_context_word_limit, 80),
        )
        if notes_excerpt:
            payload["notes"] = notes_excerpt
        return payload

    def _compact_deep_facts(self, factual_context: dict[str, Any], *, task_limit: int) -> dict[str, Any]:
        compacted: dict[str, Any] = {}
        for key in ("summary", "daily", "weekly"):
            value = factual_context.get(key)
            if isinstance(value, dict):
                compacted[self._summary_alias(key)] = self._compact_summary_block(
                    value,
                    task_limit=task_limit,
                    include_text=True,
                )

        task_value = factual_context.get("task")
        if isinstance(task_value, dict):
            compacted["task"] = self._compact_task(task_value)

        tasks_value = factual_context.get("tasks")
        if isinstance(tasks_value, list):
            compacted["top"] = self._compact_task_list(tasks_value, limit=task_limit)

        for key, value in factual_context.items():
            if key in compacted or key in {"task", "tasks"}:
                continue
            if isinstance(value, str):
                cleaned = self._clean_text(value, word_limit=40)
                if cleaned:
                    compacted[key] = cleaned
            elif isinstance(value, (int, float, bool)):
                compacted[key] = value
        return compacted

    def _build_fast_facts_block(self, factual_context: dict[str, Any]) -> str:
        task = factual_context.get("task")
        if isinstance(task, dict):
            return f"task:{self._task_label(task)}"

        for key in ("summary", "daily", "weekly"):
            value = factual_context.get(key)
            if isinstance(value, dict):
                label = self._summary_alias(key)
                block = self._summary_fact_block(value, task_limit=self._settings.fast_context_task_limit)
                if block:
                    return f"{label}:{block}"

        tasks = factual_context.get("tasks")
        if isinstance(tasks, list):
            top = self._compact_task_list(tasks, limit=self._settings.fast_context_task_limit)
            if top:
                return "top:" + ";".join(self._task_label(item) for item in top)
        return "none"

    def _summary_fact_block(self, summary: dict[str, Any], *, task_limit: int) -> str:
        parts: list[str] = []
        for key, alias in (
            ("task_count", "tc"),
            ("high_priority_count", "hp"),
            ("overdue_count", "od"),
            ("due_soon_count", "ds"),
            ("deadline_count", "dl"),
            ("repeat_count", "rp"),
            ("count", "ct"),
        ):
            value = summary.get(key)
            if isinstance(value, int):
                parts.append(f"{alias}={value}")

        windows = self._compact_windows(summary.get("free_windows"), limit=1)
        if windows:
            parts.append(f"free={windows[0]}")

        top_items: list[dict[str, Any]] = []
        for group_key in self._TASK_GROUP_FIELDS:
            group = summary.get(group_key)
            if isinstance(group, list):
                top_items.extend(self._compact_task_list(group, limit=task_limit))
                break
        if top_items:
            parts.append("top=" + ";".join(self._task_label(item) for item in top_items[:task_limit]))

        overloaded_days = self._compact_day_buckets(summary.get("overloaded_days"), limit=1)
        if overloaded_days:
            day = overloaded_days[0]
            parts.append(f"busy={day.get('date')}:{day.get('task_count', 0)}")

        light_days = self._compact_day_buckets(summary.get("light_days"), limit=1)
        if light_days:
            day = light_days[0]
            parts.append(f"light={day.get('date')}:{day.get('task_count', 0)}")

        if not parts:
            text = self._clean_text(summary.get("text"), word_limit=20)
            if text:
                parts.append(f"t={text}")
        return " ".join(parts)

    def _compact_summary_block(self, summary: dict[str, Any], *, task_limit: int, include_text: bool) -> dict[str, Any]:
        compacted: dict[str, Any] = {}
        for key in ("date", "start_date", "end_date"):
            if summary.get(key):
                compacted[self._summary_key_alias(key)] = summary[key]

        for key, alias in (
            ("task_count", "tc"),
            ("high_priority_count", "hp"),
            ("overdue_count", "od"),
            ("due_soon_count", "ds"),
            ("deadline_count", "dl"),
            ("repeat_count", "rp"),
            ("count", "ct"),
        ):
            value = summary.get(key)
            if isinstance(value, int):
                compacted[alias] = value

        if include_text:
            text = self._clean_text(summary.get("text"), word_limit=24)
            if text:
                compacted["t"] = text

        suggestions = self._compact_strings(summary.get("suggestions"), limit=2, word_limit=18)
        if suggestions:
            compacted["sg"] = suggestions

        free_windows = self._compact_windows(summary.get("free_windows"), limit=2)
        if free_windows:
            compacted["fw"] = free_windows

        for key, alias in (("items", "items"), ("overdue", "od_items"), ("due_soon", "soon")):
            items = summary.get(key)
            if isinstance(items, list):
                compacted[alias] = self._compact_task_list(items, limit=task_limit)

        overloaded_days = self._compact_day_buckets(summary.get("overloaded_days"), limit=2)
        if overloaded_days:
            compacted["busy"] = overloaded_days

        light_days = self._compact_day_buckets(summary.get("light_days"), limit=2)
        if light_days:
            compacted["light"] = light_days

        conflicts = summary.get("conflicts")
        if isinstance(conflicts, list):
            compacted["cc"] = len(conflicts)

        return compacted

    def _compact_task_list(self, items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[tuple[str | None, str | None, str | None]] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            compacted = self._compact_task(item)
            if not compacted:
                continue
            key = (
                compacted.get("title"),
                compacted.get("scheduled_date"),
                compacted.get("due_at"),
            )
            if key in seen:
                continue
            seen.add(key)
            results.append(compacted)
            if len(results) >= limit:
                break
        return results

    def _compact_task(self, task: dict[str, Any]) -> dict[str, Any]:
        compacted: dict[str, Any] = {}
        for key, alias in (
            ("title", "title"),
            ("status", "st"),
            ("priority", "p"),
            ("scheduled_date", "sd"),
            ("start_at", "sa"),
            ("due_at", "du"),
            ("repeat_rule", "rr"),
        ):
            value = task.get(key)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, str):
                compacted[alias] = self._clean_text(value, word_limit=8 if key == "title" else 8)
            else:
                compacted[alias] = value
        return compacted

    def _compact_day_buckets(self, items: Any, *, limit: int) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []
        results: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            bucket: dict[str, Any] = {}
            if item.get("date"):
                bucket["date"] = item["date"]
            if isinstance(item.get("task_count"), int):
                bucket["task_count"] = item["task_count"]
            top_items = item.get("items")
            if isinstance(top_items, list):
                bucket["top_tasks"] = self._compact_task_list(top_items, limit=2)
            if bucket:
                results.append(bucket)
            if len(results) >= limit:
                break
        return results

    def _compact_windows(self, windows: Any, *, limit: int) -> list[str]:
        if not isinstance(windows, list):
            return []
        results: list[str] = []
        seen: set[str] = set()
        for item in windows:
            if not isinstance(item, dict):
                continue
            start = self._clean_text(item.get("start"))
            end = self._clean_text(item.get("end"))
            if not start or not end:
                continue
            label = f"{start}-{end}"
            if label in seen:
                continue
            seen.add(label)
            results.append(label)
            if len(results) >= limit:
                break
        return results

    def _compact_memory(self, items: list[dict[str, Any]]) -> list[dict[str, str]]:
        results: list[str] = []
        seen: set[str] = set()
        for item in items[: self._settings.long_term_memory_limit]:
            if not isinstance(item, dict):
                continue
            category = self._clean_text(item.get("category"), word_limit=4)
            content = self._clean_text(item.get("content"), word_limit=12)
            if not content:
                continue
            label = f"{category}:{content}" if category else content
            key = label
            if key in seen:
                continue
            seen.add(key)
            results.append(label)
        return results

    def _compact_strings(self, items: Any, *, limit: int, word_limit: int) -> list[str]:
        if not isinstance(items, list):
            return []
        results: list[str] = []
        seen: set[str] = set()
        for item in items:
            cleaned = self._clean_text(item, word_limit=word_limit)
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            results.append(cleaned)
            if len(results) >= limit:
                break
        return results

    def _join_lines(self, text: Any, *, line_limit: int, word_limit: int) -> str | None:
        if not isinstance(text, str):
            return None
        results: list[str] = []
        seen: set[str] = set()
        for raw_line in text.splitlines():
            cleaned = self._clean_text(raw_line, word_limit=word_limit)
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            results.append(cleaned)
            if len(results) >= line_limit:
                break
        if not results:
            return None
        return " || ".join(results)

    def _clean_text(self, value: Any, *, word_limit: int | None = None) -> str | None:
        if value is None:
            return None
        text = " ".join(str(value).split())
        if not text:
            return None
        if word_limit is not None:
            words = text.split()
            if len(words) > word_limit:
                text = " ".join(words[:word_limit])
        return text

    def _summary_alias(self, key: str) -> str:
        mapping = {
            "summary": "sum",
            "daily": "day",
            "weekly": "week",
        }
        return mapping.get(key, key)

    def _summary_key_alias(self, key: str) -> str:
        mapping = {
            "date": "d",
            "start_date": "sd",
            "end_date": "ed",
        }
        return mapping.get(key, key)

    def _task_label(self, task: dict[str, Any]) -> str:
        title = self._clean_text(task.get("title"), word_limit=6) or "task"
        details = [
            self._clean_text(task.get("priority"), word_limit=2),
            self._clean_text(task.get("scheduled_date"), word_limit=2),
            self._clean_text(task.get("due_at"), word_limit=2),
        ]
        suffix = "|".join(item for item in details if item)
        return f"{title}|{suffix}" if suffix else title
