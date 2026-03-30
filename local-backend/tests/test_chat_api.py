from __future__ import annotations

from datetime import timedelta

from app.core.time import iso_date, now_local


def test_chat_answers_today_summary(client) -> None:
    day = now_local().date()
    client.post(
        "/v1/tasks",
        json={
            "title": "Lam slide demo",
            "status": "planned",
            "priority": "high",
            "scheduled_date": iso_date(day),
            "repeat_rule": "none",
            "tags": [],
        },
    )

    response = client.post(
        "/v1/chat",
        json={
            "message": "Hôm nay tôi có gì?",
            "conversation_id": None,
            "mode": "text",
            "selected_date": iso_date(day),
            "include_voice": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["emotion"] == "serious"
    assert payload["cards"][0]["type"] == "today_summary"
    assert "Hôm nay" in payload["reply_text"]


def test_chat_can_create_complete_and_reschedule_tasks(client) -> None:
    create_response = client.post(
        "/v1/chat",
        json={
            "message": "Thêm task họp nhóm lúc 2 giờ chiều mai",
            "conversation_id": None,
            "mode": "text",
            "selected_date": None,
            "include_voice": False,
        },
    )
    assert create_response.status_code == 200
    created_payload = create_response.json()
    assert created_payload["task_actions"][0]["type"] == "create_task"
    task_id = created_payload["task_actions"][0]["task_id"]

    complete_response = client.post(
        "/v1/chat",
        json={
            "message": "Đánh dấu họp nhóm là xong",
            "conversation_id": created_payload["conversation_id"],
            "mode": "text",
            "selected_date": None,
            "include_voice": False,
        },
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["task_actions"][0]["type"] == "complete_task"

    reopen = client.put(f"/v1/tasks/{task_id}", json={"status": "planned"})
    assert reopen.status_code == 200

    reschedule_response = client.post(
        "/v1/chat",
        json={
            "message": "Dời họp nhóm sang thứ sáu",
            "conversation_id": created_payload["conversation_id"],
            "mode": "text",
            "selected_date": None,
            "include_voice": False,
        },
    )
    assert reschedule_response.status_code == 200
    assert reschedule_response.json()["task_actions"][0]["type"] == "reschedule_task"


def test_chat_priority_update(client) -> None:
    day = now_local().date() + timedelta(days=1)
    create_response = client.post(
        "/v1/tasks",
        json={
            "title": "Bao cao tuan",
            "status": "planned",
            "priority": "medium",
            "scheduled_date": iso_date(day),
            "repeat_rule": "none",
            "tags": [],
        },
    )
    task_id = create_response.json()["id"]

    response = client.post(
        "/v1/chat",
        json={
            "message": "Tăng ưu tiên báo cáo tuần lên cao",
            "conversation_id": None,
            "mode": "text",
            "selected_date": None,
            "include_voice": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["task_actions"][0]["type"] == "priority_task"

    task = client.get(f"/v1/tasks/week?start_date={iso_date(day)}").json()
    flattened = [item for day_bucket in task["days"] for item in day_bucket["items"]]
    updated = next(item for item in flattened if item["id"] == task_id)
    assert updated["priority"] == "high"


def test_chat_falls_back_to_text_when_tts_fails(client) -> None:
    def fail_synthesize(text: str, voice: str | None = None, cache: bool = True):
        raise RuntimeError("tts offline")

    client.app.state.container.speech_service.synthesize = fail_synthesize

    response = client.post(
        "/v1/chat",
        json={
            "message": "Add task fallback coverage tomorrow",
            "conversation_id": None,
            "mode": "text",
            "selected_date": None,
            "include_voice": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply_text"]
    assert payload["speak"] is False
    assert payload["audio_url"] is None
    assert payload["task_actions"][0]["type"] == "create_task"
