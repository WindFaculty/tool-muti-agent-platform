from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_smoke_backend_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "smoke_backend.py"
    spec = importlib.util.spec_from_file_location("smoke_backend_script", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load smoke backend script from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke_backend = _load_smoke_backend_module()


def test_run_returns_summary_when_health_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    health_payload = {
        "status": "partial",
        "degraded_features": ["tts"],
        "recovery_actions": ["Fix TTS runtime"],
    }
    task_payload = {"task": {"id": "task-123"}, "events": ["created"]}
    degraded_payload = {"tts_unavailable_status": 503}
    stream_payload = {"seen_types": ["assistant_final"]}

    async def fake_wait_for_health(base_url: str, timeout: float, wait_seconds: float):
        assert base_url == "http://127.0.0.1:8096"
        assert timeout == 15.0
        assert wait_seconds == 15.0
        return health_payload

    async def fake_task_flows(base_url: str, timeout: float, title: str):
        assert title.startswith("Smoke task ")
        return task_payload

    async def fake_degraded(base_url: str, timeout: float, health: dict[str, object]):
        assert health is health_payload
        return degraded_payload

    async def fake_stream(base_url: str, timeout: float, selected_date: str):
        assert selected_date
        return stream_payload

    monkeypatch.setattr(smoke_backend, "_wait_for_health", fake_wait_for_health)
    monkeypatch.setattr(smoke_backend, "_exercise_task_flows", fake_task_flows)
    monkeypatch.setattr(smoke_backend, "_exercise_degraded_endpoints", fake_degraded)
    monkeypatch.setattr(smoke_backend, "_exercise_stream", fake_stream)

    summary = smoke_backend.asyncio.run(smoke_backend._run("http://127.0.0.1:8096", 15.0, {"ready", "partial"}))

    assert summary == {
        "health_status": "partial",
        "degraded_features": ["tts"],
        "task_id": "task-123",
        "events": task_payload,
        "stream": stream_payload,
        "degraded_checks": degraded_payload,
        "recovery_actions": ["Fix TTS runtime"],
    }


def test_run_rejects_disallowed_health_status(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_wait_for_health(base_url: str, timeout: float, wait_seconds: float):
        return {"status": "error"}

    monkeypatch.setattr(smoke_backend, "_wait_for_health", fake_wait_for_health)

    with pytest.raises(RuntimeError, match="Health status 'error' is not in allowed set"):
        smoke_backend.asyncio.run(smoke_backend._run("http://127.0.0.1:8096", 15.0, {"ready", "partial"}))


def test_wait_for_health_reports_actionable_message(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"count": 0}

    class FakeConnectError(Exception):
        pass

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"status": "ready"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, path: str):
            attempts["count"] += 1
            raise smoke_backend.httpx.ConnectError("connection refused")

    clock = {"time": 0.0}

    class FakeLoop:
        def time(self) -> float:
            clock["time"] += 0.6
            return clock["time"]

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(smoke_backend.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(smoke_backend.asyncio, "get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr(smoke_backend.asyncio, "sleep", fake_sleep)

    with pytest.raises(RuntimeError, match="Could not reach backend health at http://127.0.0.1:8096/v1/health"):
        smoke_backend.asyncio.run(smoke_backend._wait_for_health("http://127.0.0.1:8096", 1.0, wait_seconds=1.0))

    assert attempts["count"] >= 1


def test_exercise_degraded_endpoints_handles_available_and_unavailable_runtimes(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[tuple[str, str, dict[str, object]]] = []

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"unexpected status {self.status_code}")

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, path: str, json=None, files=None):
            payload = json if json is not None else files
            requests.append(("POST", path, payload))
            if path == "/v1/speech/tts" and json and json["text"] == "smoke ready tts":
                return FakeResponse(200, {"audio_url": "/audio/smoke.wav"})
            if path == "/v1/speech/stt?language=vi" and files is not None:
                if len(requests) == 2:
                    return FakeResponse(200, {"text": "xin chao"})
                return FakeResponse(503, {"detail": "stt unavailable"})
            if path == "/v1/speech/tts" and json and json["text"] == "smoke degraded tts":
                return FakeResponse(503, {"detail": "tts unavailable"})
            raise AssertionError(f"Unexpected request: {path} {payload}")

    monkeypatch.setattr(smoke_backend.httpx, "AsyncClient", FakeAsyncClient)

    available = smoke_backend.asyncio.run(
        smoke_backend._exercise_degraded_endpoints(
            "http://127.0.0.1:8096",
            10.0,
            {"runtimes": {"tts": {"available": True}, "stt": {"available": True}}},
        )
    )
    unavailable = smoke_backend.asyncio.run(
        smoke_backend._exercise_degraded_endpoints(
            "http://127.0.0.1:8096",
            10.0,
            {"runtimes": {"tts": {"available": False}, "stt": {"available": False}}},
        )
    )

    assert available == {"tts_available_status": 200, "stt_available_status": 200}
    assert unavailable == {"tts_unavailable_status": 503, "stt_unavailable_status": 503}


def test_exercise_degraded_endpoints_rejects_health_endpoint_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"unexpected status {self.status_code}")

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, path: str, json=None, files=None):
            if path == "/v1/speech/tts":
                return FakeResponse(503, {"detail": "tts unavailable"})
            raise AssertionError(f"Unexpected request: {path}")

    monkeypatch.setattr(smoke_backend.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(RuntimeError, match="unexpected status 503"):
        smoke_backend.asyncio.run(
            smoke_backend._exercise_degraded_endpoints(
                "http://127.0.0.1:8096",
                10.0,
                {"runtimes": {"tts": {"available": True}, "stt": {"available": False}}},
            )
        )
