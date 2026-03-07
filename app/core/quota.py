from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.core.errors import RateLimitError


class QuotaManager:
    def __init__(self, requests_per_minute: int, max_concurrent_per_agent: int) -> None:
        self.requests_per_minute = requests_per_minute
        self.max_concurrent_per_agent = max_concurrent_per_agent
        self._history: dict[str, deque[float]] = defaultdict(deque)
        self._in_flight: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def acquire(self, agent_id: str) -> None:
        now = time.monotonic()
        with self._lock:
            queue = self._history[agent_id]
            while queue and (now - queue[0]) > 60:
                queue.popleft()

            if len(queue) >= self.requests_per_minute:
                raise RateLimitError("Request quota exceeded for agent")

            if self._in_flight[agent_id] >= self.max_concurrent_per_agent:
                raise RateLimitError("Concurrent execution quota exceeded for agent")

            queue.append(now)
            self._in_flight[agent_id] += 1

    def release(self, agent_id: str) -> None:
        with self._lock:
            if self._in_flight[agent_id] > 0:
                self._in_flight[agent_id] -= 1

    def snapshot(self, agent_id: str) -> dict[str, int]:
        now = time.monotonic()
        with self._lock:
            queue = self._history[agent_id]
            while queue and (now - queue[0]) > 60:
                queue.popleft()

            return {
                "requests_last_minute": len(queue),
                "in_flight": self._in_flight[agent_id],
                "requests_per_minute": self.requests_per_minute,
                "max_concurrent_per_agent": self.max_concurrent_per_agent,
            }

