from __future__ import annotations

import json


class _Reply:
    def __init__(self, text: str, token_usage: dict[str, int]) -> None:
        self.text = text
        self.token_usage = token_usage


def _fake_complete_factory(captured: list[dict[str, object]]):
    def fake_complete(*, provider, system_prompt, user_prompt, json_output=False, temperature=None):
        payload = json.loads(user_prompt)
        captured.append(
            {
                "provider": provider,
                "json_output": json_output,
                "payload": payload,
            }
        )
        token_usage = {
            "input_tokens": max(1, len(system_prompt) // 4) + max(1, len(user_prompt) // 4),
            "output_tokens": 24,
        }
        if json_output:
            assert "facts" in payload
            assert "notes_context" not in payload
            assert "factual_context" not in payload
            assert "long_term_memory" not in payload
            assert "rolling_summary" not in payload
            return _Reply(
                json.dumps(
                    {
                        "intent": "planning",
                        "task_type": "planning",
                        "reasoning_summary": "stub",
                        "actionable_plan": ["step 1", "step 2"],
                        "task_actions": [],
                        "spoken_brief": "Ke hoach ngan gon.",
                        "ui_cards": [],
                        "memory_candidates": [],
                    },
                    ensure_ascii=False,
                ),
                token_usage,
            )
        assert "facts" in payload
        assert "factual_context" not in payload
        assert "rolling_summary" not in payload
        assert "long_term_memory" not in payload
        return _Reply("Tra loi ngan gon.", token_usage)

    return fake_complete


def test_chat_compacts_fast_and_deep_payloads(client) -> None:
    container = client.app.state.container
    container.llm_service.provider_available = lambda provider: True
    captured: list[dict[str, object]] = []
    container.llm_service.complete = _fake_complete_factory(captured)

    create_response = client.post(
        "/v1/chat",
        json={
            "message": "Them task hop nhom luc 2 gio chieu mai",
            "conversation_id": None,
            "mode": "text",
            "selected_date": None,
            "include_voice": False,
        },
    )
    assert create_response.status_code == 200
    create_payload = create_response.json()

    complete_response = client.post(
        "/v1/chat",
        json={
            "message": "Danh dau hop nhom la xong",
            "conversation_id": create_payload["conversation_id"],
            "mode": "text",
            "selected_date": None,
            "include_voice": False,
        },
    )
    assert complete_response.status_code == 200

    task_id = create_payload["task_actions"][0]["task_id"]
    reopen = client.put(f"/v1/tasks/{task_id}", json={"status": "planned"})
    assert reopen.status_code == 200

    reschedule_response = client.post(
        "/v1/chat",
        json={
            "message": "Doi hop nhom sang thu sau luc 14h",
            "conversation_id": create_payload["conversation_id"],
            "mode": "text",
            "selected_date": None,
            "include_voice": False,
        },
    )
    assert reschedule_response.status_code == 200

    today_response = client.post(
        "/v1/chat",
        json={
            "message": "Hom nay toi co gi?",
            "conversation_id": None,
            "mode": "text",
            "selected_date": None,
            "include_voice": False,
        },
    )
    assert today_response.status_code == 200

    planning_response = client.post(
        "/v1/chat",
        json={
            "message": "Hay toi uu va lap ke hoach cho toi",
            "conversation_id": None,
            "mode": "text",
            "selected_date": None,
            "include_voice": False,
            "notes_context": " ".join(["deadline gap", "uu tien backend", "fix websocket"] * 80),
        },
    )
    assert planning_response.status_code == 200

    fast_payloads = [item["payload"] for item in captured if item["json_output"] is False]
    deep_payloads = [item["payload"] for item in captured if item["json_output"] is True]

    assert len(fast_payloads) >= 4
    assert len(deep_payloads) == 1

    for payload in fast_payloads:
        assert set(payload).issuperset({"msg", "intent", "facts"})
        assert "factual_context" not in payload
        assert isinstance(payload["facts"], str)
        if payload["facts"].startswith("task:"):
            assert "description" not in payload["facts"]

    deep_payload = deep_payloads[0]
    assert set(deep_payload).issuperset({"msg", "intent", "facts", "roll", "notes", "mem"})
    assert "factual_context" not in deep_payload
    assert "notes_context" not in deep_payload
    assert "rolling_summary" not in deep_payload
    assert "long_term_memory" not in deep_payload
    assert len(deep_payload["mem"]) <= container.settings.long_term_memory_limit
    assert len(deep_payload["facts"]["top"]) <= container.settings.deep_context_task_limit
    assert len(deep_payload["notes"].split()) <= container.settings.notes_context_word_limit
    if deep_payload["roll"] is not None:
        assert deep_payload["roll"].count("||") <= max(container.settings.rolling_summary_line_limit - 1, 0)


def test_stream_turn_keeps_token_usage_and_uses_compact_payload(client) -> None:
    container = client.app.state.container
    container.llm_service.provider_available = lambda provider: True
    captured: list[dict[str, object]] = []
    container.llm_service.complete = _fake_complete_factory(captured)

    with client.websocket_connect("/v1/assistant/stream") as websocket:
        websocket.send_json(
            {
                "type": "session_start",
                "session_id": "sess_compact",
                "selected_date": None,
                "voice_mode": False,
                "notes_context": " ".join(["deadline gap", "uu tien backend", "fix websocket"] * 80),
            }
        )
        websocket.receive_json()

        websocket.send_json(
            {
                "type": "text_turn",
                "session_id": "sess_compact",
                "conversation_id": None,
                "message": "Hay toi uu va lap ke hoach cho toi",
                "voice_mode": False,
            }
        )

        final_payload = None
        for _ in range(12):
            event = websocket.receive_json()
            if event["type"] == "assistant_final":
                final_payload = event
                break

    assert final_payload is not None
    assert final_payload["token_usage"]["input_tokens"] > 0
    assert final_payload["fallback_used"] is False
    assert captured
    deep_payload = next(item["payload"] for item in captured if item["json_output"] is True)
    assert "facts" in deep_payload
    assert "notes_context" not in deep_payload
    assert "long_term_memory" not in deep_payload
