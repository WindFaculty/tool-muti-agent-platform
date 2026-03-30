from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from app.core.time import iso_date, now_local, parse_datetime
from app.models.enums import TaskPriority
from app.services.tasks import TaskService


class PlannerService:
    def __init__(self, task_service: TaskService) -> None:
        self._task_service = task_service

    def daily_summary(self, target_date: date) -> dict[str, Any]:
        snapshot = self._task_service.list_day(target_date)
        items = snapshot["items"]
        high_priority = [
            item for item in items if item["priority"] in (TaskPriority.HIGH.value, TaskPriority.CRITICAL.value)
        ]
        free_windows = self._free_windows(target_date, items)
        suggestions = self._daily_suggestions(snapshot, high_priority)
        text = self._daily_text(target_date, items, snapshot["overdue"], high_priority, free_windows, suggestions)
        return {
            "date": iso_date(target_date),
            "task_count": len(items),
            "high_priority_count": len(high_priority),
            "overdue_count": len(snapshot["overdue"]),
            "due_soon_count": len(snapshot["due_soon"]),
            "free_windows": free_windows,
            "suggestions": suggestions,
            "items": items,
            "text": text,
        }

    def weekly_summary(self, start_date: date) -> dict[str, Any]:
        snapshot = self._task_service.list_week(start_date)
        all_items = [item for day in snapshot["days"] for item in day["items"]]
        deadlines = [item for item in all_items if item.get("due_at")]
        overloaded_days = [day for day in snapshot["days"] if day["task_count"] >= 4]
        light_days = [day for day in snapshot["days"] if day["task_count"] <= 1]
        repeat_count = len([item for item in all_items if item["repeat_rule"] != "none"])
        text = self._weekly_text(snapshot, deadlines, overloaded_days, light_days, repeat_count)
        return {
            "start_date": snapshot["start_date"],
            "end_date": snapshot["end_date"],
            "task_count": len(all_items),
            "deadline_count": len(deadlines),
            "repeat_count": repeat_count,
            "overloaded_days": overloaded_days,
            "light_days": light_days,
            "conflicts": snapshot["conflicts"],
            "text": text,
        }

    def overdue_summary(self) -> dict[str, Any]:
        overdue = self._task_service.list_overdue()["items"]
        if not overdue:
            text = "Hiện tại không có việc nào quá hạn."
        else:
            titles = ", ".join(item["title"] for item in overdue[:3])
            text = f"Bạn có {len(overdue)} việc quá hạn. Ưu tiên xử lý: {titles}."
        return {"count": len(overdue), "items": overdue, "text": text}

    def urgency_summary(self) -> dict[str, Any]:
        today = self.daily_summary(now_local().date())
        urgent = [
            item
            for item in today["items"]
            if item["priority"] == TaskPriority.CRITICAL.value
        ]
        if not urgent and today["items"]:
            urgent = [today["items"][0]]
        titles = ", ".join(item["title"] for item in urgent[:2]) if urgent else "không có việc quá gấp"
        return {"items": urgent, "text": f"Việc gấp nhất lúc này: {titles}."}

    def free_slots(self, target_date: date) -> dict[str, Any]:
        snapshot = self._task_service.list_day(target_date)
        free_windows = self._free_windows(target_date, snapshot["items"])
        if free_windows:
            windows = ", ".join(f"{slot['start']} - {slot['end']}" for slot in free_windows[:3])
            text = f"Bạn còn trống vào các khoảng: {windows}."
        else:
            text = "Ngày này hiện không còn khoảng trống rõ ràng trong khung 08:00-18:00."
        return {"date": iso_date(target_date), "free_windows": free_windows, "text": text}

    def _daily_suggestions(
        self,
        snapshot: dict[str, Any],
        high_priority: list[dict[str, Any]],
    ) -> list[str]:
        suggestions: list[str] = []
        if snapshot["overdue"]:
            suggestions.append("Chốt ít nhất 1 việc quá hạn trước khi nhận thêm việc mới.")
        if high_priority:
            suggestions.append(f"Bắt đầu với việc ưu tiên cao: {high_priority[0]['title']}.")
        if snapshot["due_soon"]:
            suggestions.append("Có việc sắp đến hạn trong vài giờ tới, nên khóa thời gian xử lý ngay.")
        return suggestions[:2]

    def _daily_text(
        self,
        target_date: date,
        items: list[dict[str, Any]],
        overdue: list[dict[str, Any]],
        high_priority: list[dict[str, Any]],
        free_windows: list[dict[str, str]],
        suggestions: list[str],
    ) -> str:
        day_name = "Hôm nay" if target_date == now_local().date() else f"Ngày {iso_date(target_date)}"
        if not items and not overdue:
            if free_windows:
                return f"{day_name} bạn chưa có việc nào được lên lịch. {self.free_slots(target_date)['text']}"
            return f"{day_name} bạn chưa có việc nào được lên lịch."

        parts = [
            f"{day_name} bạn có {len(items)} việc",
            f"trong đó {len(high_priority)} việc ưu tiên cao" if high_priority else "không có việc ưu tiên cao",
        ]
        if overdue:
            parts.append(f"và {len(overdue)} việc quá hạn")
        sentence = ", ".join(parts) + "."
        if free_windows:
            sentence += " Khoảng trống tốt nhất: " + ", ".join(
                f"{slot['start']}-{slot['end']}" for slot in free_windows[:2]
            ) + "."
        if suggestions:
            sentence += " Gợi ý: " + " ".join(suggestions)
        return sentence

    def _weekly_text(
        self,
        snapshot: dict[str, Any],
        deadlines: list[dict[str, Any]],
        overloaded_days: list[dict[str, Any]],
        light_days: list[dict[str, Any]],
        repeat_count: int,
    ) -> str:
        total = sum(day["task_count"] for day in snapshot["days"])
        parts = [f"7 ngày tới bạn có {total} việc"]
        if deadlines:
            parts.append(f"{len(deadlines)} deadline có hạn cụ thể")
        if overloaded_days:
            parts.append("ngày nặng nhất là " + ", ".join(day["date"] for day in overloaded_days[:2]))
        if light_days:
            parts.append("ngày nhẹ nhất là " + ", ".join(day["date"] for day in light_days[:2]))
        if repeat_count:
            parts.append(f"{repeat_count} việc lặp")
        if snapshot["conflicts"]:
            parts.append(f"{len(snapshot['conflicts'])} xung đột giờ")
        return ", ".join(parts) + "."

    def _free_windows(self, target_date: date, items: list[dict[str, Any]]) -> list[dict[str, str]]:
        start_of_day = datetime.combine(target_date, time(hour=8))
        end_of_day = datetime.combine(target_date, time(hour=18))
        intervals = []
        for item in items:
            start_at = parse_datetime(item.get("start_at"))
            end_at = parse_datetime(item.get("end_at"))
            if start_at and end_at:
                intervals.append((start_at, end_at))
        intervals.sort(key=lambda value: value[0])

        free_windows: list[dict[str, str]] = []
        cursor = start_of_day
        for interval_start, interval_end in intervals:
            if interval_start > cursor:
                free_windows.append(
                    {
                        "start": cursor.strftime("%H:%M"),
                        "end": interval_start.strftime("%H:%M"),
                    }
                )
            if interval_end > cursor:
                cursor = interval_end
        if cursor < end_of_day:
            free_windows.append({"start": cursor.strftime("%H:%M"), "end": end_of_day.strftime("%H:%M")})
        return free_windows
