from __future__ import annotations

import argparse
import asyncio
import json
import uuid
import wave
from datetime import datetime, timedelta
from typing import Any

import httpx
import websockets


def _http_to_ws(base_url: str, path: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.startswith("https://"):
        normalized = "wss://" + normalized[len("https://") :]
    elif normalized.startswith("http://"):
        normalized = "ws://" + normalized[len("http://") :]
    return normalized + path


def _today() -> str:
    return datetime.now().date().isoformat()


def _tomorrow() -> str:
    return (datetime.now().date() + timedelta(days=1)).isoformat()


async def _receive_json(socket: websockets.WebSocketClientProtocol, timeout: float) -> dict[str, Any]:
    raw = await asyncio.wait_for(socket.recv(), timeout=timeout)
    return json.loads(raw)


async def _expect_task_updated(
    socket: websockets.WebSocketClientProtocol,
    timeout: float,
    expected_task_id: str,
    expected_change: str,
) -> dict[str, Any]:
    event = await _receive_json(socket, timeout)
    if event.get("type") != "task_updated":
        raise RuntimeError(f"Expected task_updated event for {expected_change}, got: {event}")
    if event.get("task_id") != expected_task_id:
        raise RuntimeError(
            f"Expected task_updated for task {expected_task_id} during {expected_change}, got: {event}"
        )
    if event.get("change") != expected_change:
        raise RuntimeError(f"Expected task_updated change={expected_change}, got: {event}")
    return event


def _find_task(items: list[dict[str, Any]], task_id: str) -> dict[str, Any]:
    for item in items:
        if item.get("id") == task_id:
            return item
    raise RuntimeError(f"Task {task_id} was not found in response payload")


def _build_smoke_wav_bytes() -> bytes:
    sample_rate = 16000
    frame_count = sample_rate
    audio = b"\x00\x00" * frame_count

    import io

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(audio)
    return buffer.getvalue()


async def _exercise_task_flows(base_url: str, timeout: float, title: str) -> dict[str, Any]:
    events_url = _http_to_ws(base_url, "/v1/events")
    async with websockets.connect(events_url) as socket:
        first = await _receive_json(socket, timeout)
        if first.get("type") != "assistant_state_changed":
            raise RuntimeError(f"Unexpected first /v1/events payload: {first}")

        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            create = await client.post(
                "/v1/tasks",
                json={
                    "title": title,
                    "status": "planned",
                    "priority": "medium",
                    "scheduled_date": _today(),
                    "repeat_rule": "none",
                    "tags": ["smoke"],
                },
            )
            create.raise_for_status()
            task = create.json()
            task_id = task["id"]

            created_event = await _expect_task_updated(socket, timeout, task_id, "created")

            today_response = await client.get("/v1/tasks/today", params={"date": _today()})
            today_response.raise_for_status()
            today_payload = today_response.json()
            created_today = _find_task(today_payload.get("items", []), task_id)

            week_response = await client.get("/v1/tasks/week", params={"start_date": _today()})
            week_response.raise_for_status()
            week_payload = week_response.json()
            flat_week_items = [item for day in week_payload.get("days", []) for item in day.get("items", [])]
            _find_task(flat_week_items, task_id)

            update_response = await client.put(f"/v1/tasks/{task_id}", json={"priority": "high"})
            update_response.raise_for_status()
            updated_task = update_response.json()
            updated_event = await _expect_task_updated(socket, timeout, task_id, "updated")

            tomorrow = _tomorrow()
            reschedule_response = await client.post(
                f"/v1/tasks/{task_id}/reschedule",
                json={"scheduled_date": tomorrow},
            )
            reschedule_response.raise_for_status()
            rescheduled_task = reschedule_response.json()
            rescheduled_event = await _expect_task_updated(socket, timeout, task_id, "rescheduled")

            rescheduled_today_response = await client.get("/v1/tasks/today", params={"date": tomorrow})
            rescheduled_today_response.raise_for_status()
            rescheduled_today_payload = rescheduled_today_response.json()
            rescheduled_today = _find_task(rescheduled_today_payload.get("items", []), task_id)

            overdue_response = await client.get("/v1/tasks/overdue")
            overdue_response.raise_for_status()

            complete_response = await client.post(f"/v1/tasks/{task_id}/complete", json={})
            complete_response.raise_for_status()
            completed_task = complete_response.json()
            completed_event = await _expect_task_updated(socket, timeout, task_id, "completed")

            completed_response = await client.get("/v1/tasks/completed")
            completed_response.raise_for_status()
            completed_payload = completed_response.json()
            completed_item = _find_task(completed_payload.get("items", []), task_id)

            inbox_response = await client.get("/v1/tasks/inbox")
            inbox_response.raise_for_status()

        return {
            "task": task,
            "first_event": first,
            "events": [created_event, updated_event, rescheduled_event, completed_event],
            "task_flow": {
                "created_today_title": created_today.get("title"),
                "updated_priority": updated_task.get("priority"),
                "rescheduled_date": rescheduled_task.get("scheduled_date"),
                "rescheduled_today_title": rescheduled_today.get("title"),
                "completed_status": completed_task.get("status"),
                "completed_task_title": completed_item.get("title"),
                "overdue_count": len(overdue_response.json().get("items", [])),
                "inbox_count": len(inbox_response.json().get("items", [])),
            },
        }


async def _exercise_stream(base_url: str, timeout: float, selected_date: str) -> dict[str, Any]:
    stream_url = _http_to_ws(base_url, "/v1/assistant/stream")
    session_id = "smoke_" + uuid.uuid4().hex[:12]

    async with websockets.connect(stream_url) as socket:
        await socket.send(
            json.dumps(
                {
                    "type": "session_start",
                    "session_id": session_id,
                    "selected_date": selected_date,
                    "voice_mode": False,
                }
            )
        )
        first = await _receive_json(socket, timeout)
        if first.get("type") != "assistant_state_changed":
            raise RuntimeError(f"Unexpected first /v1/assistant/stream payload: {first}")

        await socket.send(
            json.dumps(
                {
                    "type": "text_turn",
                    "session_id": session_id,
                    "conversation_id": None,
                    "message": "Hom nay toi co gi?",
                    "selected_date": selected_date,
                    "voice_mode": False,
                }
            )
        )

        seen_types: list[str] = []
        final_payload: dict[str, Any] | None = None
        for _ in range(20):
            event = await _receive_json(socket, timeout)
            event_type = str(event.get("type"))
            seen_types.append(event_type)
            if event_type == "assistant_final":
                final_payload = event
                break

        if final_payload is None:
            raise RuntimeError(f"assistant_final was not observed. Seen events: {seen_types}")

        return {"first_event": first, "seen_types": seen_types, "final": final_payload}


async def _exercise_degraded_endpoints(base_url: str, timeout: float, health: dict[str, Any]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    runtimes = health.get("runtimes", {})
    smoke_wav = _build_smoke_wav_bytes()

    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        tts = runtimes.get("tts", {})
        if tts.get("available", False):
            response = await client.post("/v1/speech/tts", json={"text": "smoke ready tts", "cache": False})
            response.raise_for_status()
            payload = response.json()
            if not payload.get("audio_url"):
                raise RuntimeError("Expected /v1/speech/tts to return an audio_url when TTS is available")
            results["tts_available_status"] = response.status_code
        else:
            response = await client.post("/v1/speech/tts", json={"text": "smoke degraded tts", "cache": True})
            if response.status_code != 503:
                raise RuntimeError(f"Expected /v1/speech/tts to return 503 when TTS is unavailable, got {response.status_code}")
            results["tts_unavailable_status"] = response.status_code

        stt = runtimes.get("stt", {})
        if stt.get("available", False):
            files = {"audio": ("smoke.wav", smoke_wav, "audio/wav")}
            response = await client.post("/v1/speech/stt?language=vi", files=files)
            response.raise_for_status()
            payload = response.json()
            if "text" not in payload:
                raise RuntimeError("Expected /v1/speech/stt to return a text field when STT is available")
            results["stt_available_status"] = response.status_code
        else:
            files = {"audio": ("smoke.wav", smoke_wav, "audio/wav")}
            response = await client.post("/v1/speech/stt?language=vi", files=files)
            if response.status_code != 503:
                raise RuntimeError(f"Expected /v1/speech/stt to return 503 when STT is unavailable, got {response.status_code}")
            results["stt_unavailable_status"] = response.status_code

    return results


async def _wait_for_health(base_url: str, timeout: float, wait_seconds: float) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + wait_seconds
    last_error: Exception | None = None

    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        while True:
            try:
                health_response = await client.get("/v1/health")
                health_response.raise_for_status()
                return health_response.json()
            except (httpx.ConnectError, httpx.HTTPError) as exc:
                last_error = exc
                if asyncio.get_running_loop().time() >= deadline:
                    break
                await asyncio.sleep(0.5)

    message = (
        f"Could not reach backend health at {base_url.rstrip('/')}/v1/health after {wait_seconds:.1f}s. "
        "Start the backend first, for example: `cd local-backend && python run_local.py`, "
        "or point --base-url to a running server."
    )
    if last_error is not None:
        message += f" Last error: {last_error}"
    raise RuntimeError(message)


async def _run(base_url: str, timeout: float, allow_health: set[str]) -> dict[str, Any]:
    health = await _wait_for_health(base_url, timeout, wait_seconds=timeout)

    status = str(health.get("status"))
    if status not in allow_health:
        raise RuntimeError(f"Health status {status!r} is not in allowed set {sorted(allow_health)}")

    title = "Smoke task " + uuid.uuid4().hex[:8]
    events = await _exercise_task_flows(base_url, timeout, title)
    task_id = events["task"]["id"]

    degraded = await _exercise_degraded_endpoints(base_url, timeout, health)
    stream = await _exercise_stream(base_url, timeout, _today())

    return {
        "health_status": health.get("status"),
        "degraded_features": health.get("degraded_features", []),
        "task_id": task_id,
        "events": events,
        "stream": stream,
        "degraded_checks": degraded,
        "recovery_actions": health.get("recovery_actions", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repeatable local backend smoke checks.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8096")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--allow-health-status",
        nargs="+",
        default=["ready", "partial"],
        help="Allowed health statuses for the smoke run.",
    )
    args = parser.parse_args()

    try:
        summary = asyncio.run(_run(args.base_url, args.timeout, set(args.allow_health_status)))
    except RuntimeError as exc:
        print(f"Smoke check failed: {exc}")
        return 1

    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
