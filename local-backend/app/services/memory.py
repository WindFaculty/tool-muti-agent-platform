from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.core.ids import make_id
from app.core.time import iso_datetime, now_local
from app.db.repository import SQLiteRepository


class MemoryService:
    def __init__(self, repository: SQLiteRepository, short_term_turn_limit: int = 12) -> None:
        self._repository = repository
        self._short_term_turn_limit = short_term_turn_limit

    def recent_messages(self, conversation_id: str | None) -> list[dict[str, Any]]:
        if not conversation_id:
            return []
        messages = self._repository.list_messages(conversation_id)
        max_messages = self._short_term_turn_limit * 2
        return messages[-max_messages:]

    def rolling_summary(self, conversation_id: str | None) -> str:
        if not conversation_id:
            return ""
        summary = self._repository.get_conversation_summary(conversation_id)
        return str(summary["summary_text"]) if summary else ""

    def refresh_summary(self, conversation_id: str | None) -> str:
        if not conversation_id:
            return ""
        messages = self.recent_messages(conversation_id)
        if not messages:
            return ""
        summary_lines = []
        for item in messages[-8:]:
            role = "User" if item["role"] == "user" else "Assistant"
            content = " ".join(str(item["content"]).split())
            if len(content) > 120:
                content = content[:117] + "..."
            summary_lines.append(f"{role}: {content}")
        summary_text = "\n".join(summary_lines)
        self._repository.upsert_conversation_summary(
            conversation_id=conversation_id,
            summary_text=summary_text,
            turn_count=len(messages),
            updated_at=iso_datetime(now_local()),
        )
        return summary_text

    def relevant_long_term_memory(self, text: str, limit: int = 5) -> list[dict[str, Any]]:
        if not text.strip():
            return []
        query_tokens = {token for token in self._normalize(text).split() if len(token) > 2}
        ranked = []
        for item in self._repository.list_memory_items():
            haystack = self._normalize(item["content"])
            overlap = len([token for token in query_tokens if token in haystack])
            if overlap:
                ranked.append((overlap, item))
        ranked.sort(key=lambda value: (value[0], value[1]["confidence"]), reverse=True)
        return [item for _, item in ranked[:limit]]

    def extract_and_store(
        self,
        *,
        conversation_id: str | None,
        user_message: str,
        assistant_reply: str,
        enabled: bool = True,
    ) -> list[dict[str, Any]]:
        if not enabled:
            return []
        candidates = self._extract_candidates(user_message)
        now_iso = iso_datetime(now_local())
        stored = []
        for candidate in candidates:
            if candidate["confidence"] < 0.7:
                continue
            payload = {
                "id": make_id("mem"),
                "category": candidate["category"],
                "normalized_key": self._normalize(candidate["key"]),
                "content": candidate["content"],
                "confidence": candidate["confidence"],
                "status": "active",
                "metadata_json": {
                    "source": "auto_extract",
                    "assistant_reply": assistant_reply,
                },
                "source_conversation_id": conversation_id,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            self._repository.upsert_memory_item(payload)
            stored.append(payload)
        return stored

    def _extract_candidates(self, text: str) -> list[dict[str, Any]]:
        lowered = self._normalize(text)
        patterns = [
            ("preference", r"\btoi thich\s+(.+)", 0.82),
            ("routine", r"\btoi thuong\s+(.+)", 0.78),
            ("project", r"\btoi dang lam\s+(.+)", 0.84),
            ("goal", r"\bmuc tieu(?: cua toi)? la\s+(.+)", 0.88),
        ]
        candidates = []
        for category, pattern, confidence in patterns:
            match = re.search(pattern, lowered)
            if not match:
                continue
            content = match.group(1).strip(" .")
            if len(content) < 4:
                continue
            key = content[:80]
            candidates.append(
                {
                    "category": category,
                    "key": key,
                    "content": content,
                    "confidence": confidence,
                }
            )
        return candidates

    def _normalize(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value.casefold())
        return "".join(ch for ch in normalized if not unicodedata.combining(ch)).strip()
