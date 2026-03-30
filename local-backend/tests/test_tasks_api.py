from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from app.core.time import iso_date, iso_datetime, now_local


def test_health_reports_partial_when_runtimes_missing(client) -> None:
    response = client.get("/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["runtimes"]["llm"]["provider"] == "hybrid"
    assert payload["runtimes"]["llm"]["reason"] == "no_provider_available"
    assert "llm" in payload["degraded_features"]
    assert "stt" in payload["degraded_features"]
    assert "tts" in payload["degraded_features"]
    assert payload["logs"]["app_log"].endswith("assistant.log")
    assert Path(payload["logs"]["app_log"]).exists()
    assert any("fast provider groq and deep provider gemini" in action for action in payload["recovery_actions"])
    assert any("assistant_whisper_command" in action for action in payload["recovery_actions"])
    assert any("assistant_piper_command" in action for action in payload["recovery_actions"])


def test_health_reports_ready_when_database_and_runtimes_are_available(client) -> None:
    container = client.app.state.container
    container.llm_service.health = lambda: {
        "available": True,
        "provider": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "stub",
    }
    container.speech_service.stt_health = lambda: {"available": True, "provider": "whisper.cpp"}
    container.speech_service.tts_health = lambda: {"available": True, "provider": "piper"}

    response = client.get("/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["database"]["available"] is True
    assert payload["runtimes"]["llm"]["provider"] == "groq"
    assert payload["degraded_features"] == []
    assert payload["recovery_actions"] == []


def test_health_reports_partial_when_runtime_model_paths_are_missing(client) -> None:
    container = client.app.state.container
    container.llm_service.health = lambda: {
        "available": True,
        "provider": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "stub",
    }
    container.speech_service.stt_health = lambda: {
        "available": False,
        "provider": "whisper.cpp",
        "command": "C:\\runtime\\whisper-cli.exe",
        "model_path": "C:\\runtime\\models",
        "reason": "model_path_not_configured_or_not_found",
        "issues": ["model_path_not_configured_or_not_found"],
    }
    container.speech_service.tts_health = lambda: {
        "available": False,
        "provider": "piper",
        "command": "C:\\runtime\\piper.exe",
        "model_path": "C:\\runtime\\voices",
        "reason": "model_path_not_configured_or_not_found",
        "issues": ["model_path_not_configured_or_not_found"],
    }

    response = client.get("/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["degraded_features"] == ["stt", "tts"]
    assert any("assistant_whisper_command" in action for action in payload["recovery_actions"])
    assert any("assistant_piper_command" in action for action in payload["recovery_actions"])


def test_health_reports_partial_when_speech_endpoint_uses_fallback_provider(client) -> None:
    container = client.app.state.container
    container.llm_service.health = lambda: {
        "available": True,
        "provider": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "stub",
    }
    container.speech_service.stt_health = lambda: {
        "available": True,
        "provider": "faster-whisper",
        "provider_available": False,
        "effective_provider": "whisper.cpp",
        "fallback": {"available": True, "provider": "whisper.cpp"},
        "reason": "probe_failed",
        "error": "missing cublas64_12.dll",
    }
    container.speech_service.tts_health = lambda: {"available": True, "provider": "piper"}

    response = client.get("/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert "stt" in payload["degraded_features"]
    assert any("assistant_whisper_command" in action for action in payload["recovery_actions"])


def test_health_reports_error_when_database_is_unavailable(client) -> None:
    container = client.app.state.container
    container.repository.health_check = lambda: {
        "available": False,
        "path": str(container.settings.db_path),
        "error": "database unavailable",
    }

    response = client.get("/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["database"]["available"] is False
    assert any("SQLite path" in action for action in payload["recovery_actions"])


def test_task_crud_and_today_completed_views(client) -> None:
    day = now_local().date()
    create_response = client.post(
        "/v1/tasks",
        json={
            "title": "Bao cao sprint",
            "description": "Tong hop tien do",
            "status": "planned",
            "priority": "high",
            "scheduled_date": iso_date(day),
            "start_at": iso_datetime(now_local().replace(hour=14, minute=0, second=0)),
            "end_at": iso_datetime(now_local().replace(hour=15, minute=0, second=0)),
            "repeat_rule": "none",
            "tags": ["work"],
        },
    )
    assert create_response.status_code == 200
    task = create_response.json()

    today_response = client.get(f"/v1/tasks/today?date={iso_date(day)}")
    assert today_response.status_code == 200
    today_payload = today_response.json()
    assert any(item["id"] == task["id"] for item in today_payload["items"])

    update_response = client.put(f"/v1/tasks/{task['id']}", json={"priority": "critical"})
    assert update_response.status_code == 200
    assert update_response.json()["priority"] == "critical"

    complete_response = client.post(f"/v1/tasks/{task['id']}/complete", json={})
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "done"

    completed_response = client.get("/v1/tasks/completed")
    assert completed_response.status_code == 200
    assert any(item["id"] == task["id"] for item in completed_response.json()["items"])


def test_week_view_detects_conflicts_and_recurring_items(client) -> None:
    base_day = now_local().date()
    client.post(
        "/v1/tasks",
        json={
            "title": "Hop team",
            "status": "planned",
            "priority": "medium",
            "scheduled_date": iso_date(base_day),
            "start_at": iso_datetime(now_local().replace(hour=9, minute=0, second=0)),
            "end_at": iso_datetime(now_local().replace(hour=10, minute=0, second=0)),
            "repeat_rule": "daily",
            "tags": [],
        },
    )
    client.post(
        "/v1/tasks",
        json={
            "title": "Review tai lieu",
            "status": "planned",
            "priority": "medium",
            "scheduled_date": iso_date(base_day),
            "start_at": iso_datetime(now_local().replace(hour=9, minute=30, second=0)),
            "end_at": iso_datetime(now_local().replace(hour=10, minute=30, second=0)),
            "repeat_rule": "none",
            "tags": [],
        },
    )

    week_response = client.get(f"/v1/tasks/week?start_date={iso_date(base_day)}")
    assert week_response.status_code == 200
    week_payload = week_response.json()
    assert week_payload["conflicts"]
    assert sum(day["task_count"] for day in week_payload["days"]) >= 3


def test_overdue_view_lists_past_due_items(client) -> None:
    yesterday = now_local() - timedelta(days=1)
    response = client.post(
        "/v1/tasks",
        json={
            "title": "Nop hoa don",
            "status": "planned",
            "priority": "high",
            "scheduled_date": iso_date(yesterday.date()),
            "due_at": iso_datetime(yesterday),
            "repeat_rule": "none",
            "tags": [],
        },
    )
    assert response.status_code == 200
    overdue = client.get("/v1/tasks/overdue")
    assert overdue.status_code == 200
    assert overdue.json()["items"][0]["title"] == "Nop hoa don"
