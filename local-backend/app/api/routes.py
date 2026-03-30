from __future__ import annotations

import base64
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.container import AppContainer
from app.core.ids import make_id
from app.core.time import iso_date
from app.core.health import build_logs_payload, build_recovery_actions
from app.core.logging import get_logger
from app.models.schemas import (
    AssistantStreamMessage,
    ChatRequest,
    ChatResponse,
    CompleteTaskRequest,
    HealthResponse,
    RescheduleTaskRequest,
    SettingsPayload,
    SpeechSttResponse,
    SpeechTtsRequest,
    SpeechTtsResponse,
    TaskCreateRequest,
    TaskUpdateRequest,
)

router = APIRouter(prefix="/v1")
logger = get_logger("api")


def _container(request: Request) -> AppContainer:
    return request.app.state.container


def _parse_day(day_value: str | None) -> date:
    if day_value:
        return date.fromisoformat(day_value)
    from app.core.time import now_local

    return now_local().date()


def _runtime_is_degraded(runtime_payload: dict[str, Any]) -> bool:
    if not runtime_payload.get("available", False):
        return True
    provider_available = runtime_payload.get("provider_available")
    return provider_available is False


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    container = _container(request)
    database = container.repository.health_check()
    llm = container.llm_service.health()
    stt = container.speech_service.stt_health()
    tts = container.speech_service.tts_health()
    recovery_actions = build_recovery_actions(container.settings, database, llm, stt, tts)
    degraded = []
    if not llm["available"]:
        degraded.append("llm")
    if _runtime_is_degraded(stt):
        degraded.append("stt")
    if _runtime_is_degraded(tts):
        degraded.append("tts")
    status = "ready"
    if not database["available"]:
        status = "error"
    elif degraded:
        status = "partial"
    return HealthResponse(
        status=status,
        service=container.settings.app_name,
        version=container.settings.app_version,
        database=database,
        runtimes={"llm": llm, "stt": stt, "tts": tts},
        degraded_features=degraded,
        logs=build_logs_payload(container.settings),
        recovery_actions=recovery_actions,
    )


@router.get("/tasks/today")
async def tasks_today(request: Request, date: str | None = Query(default=None)) -> dict[str, Any]:
    return _container(request).task_service.list_day(_parse_day(date))


@router.get("/tasks/week")
async def tasks_week(request: Request, start_date: str | None = Query(default=None)) -> dict[str, Any]:
    return _container(request).task_service.list_week(_parse_day(start_date))


@router.get("/tasks/overdue")
async def tasks_overdue(request: Request) -> dict[str, Any]:
    return _container(request).task_service.list_overdue()


@router.get("/tasks/inbox")
async def tasks_inbox(request: Request, limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return _container(request).task_service.list_inbox(limit=limit)


@router.get("/tasks/completed")
async def tasks_completed(request: Request, limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return _container(request).task_service.list_completed(limit=limit)


@router.post("/tasks")
async def create_task(request: Request, payload: TaskCreateRequest) -> dict[str, Any]:
    try:
        task = _container(request).task_service.create_task(payload)
    except ValueError as exc:
        logger.warning("Task creation rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _container(request).event_bus.publish({"type": "task_updated", "task_id": task.id, "change": "created"})
    return task.model_dump()


@router.put("/tasks/{task_id}")
async def update_task(request: Request, task_id: str, payload: TaskUpdateRequest) -> dict[str, Any]:
    try:
        task = _container(request).task_service.update_task(task_id, payload)
    except LookupError as exc:
        logger.warning("Task update failed for %s: %s", task_id, exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning("Task update rejected for %s: %s", task_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _container(request).event_bus.publish({"type": "task_updated", "task_id": task.id, "change": "updated"})
    return task.model_dump()


@router.post("/tasks/{task_id}/complete")
async def complete_task(request: Request, task_id: str, payload: CompleteTaskRequest) -> dict[str, Any]:
    try:
        task = _container(request).task_service.complete_task(task_id, payload)
    except LookupError as exc:
        logger.warning("Task completion failed for %s: %s", task_id, exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await _container(request).event_bus.publish({"type": "task_updated", "task_id": task.id, "change": "completed"})
    return task.model_dump()


@router.post("/tasks/{task_id}/reschedule")
async def reschedule_task(request: Request, task_id: str, payload: RescheduleTaskRequest) -> dict[str, Any]:
    try:
        task = _container(request).task_service.reschedule_task(task_id, payload)
    except LookupError as exc:
        logger.warning("Task reschedule failed for %s: %s", task_id, exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning("Task reschedule rejected for %s: %s", task_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _container(request).event_bus.publish({"type": "task_updated", "task_id": task.id, "change": "rescheduled"})
    return task.model_dump()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    try:
        return await _container(request).conversation_service.handle_chat(payload)
    except LookupError as exc:
        logger.warning("Chat task lookup failed: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning("Chat validation failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/speech/stt", response_model=SpeechSttResponse)
async def speech_stt(
    request: Request,
    audio: UploadFile = File(...),
    language: str | None = None,
) -> SpeechSttResponse:
    container = _container(request)
    original_name = Path(audio.filename or "input.wav").name or "input.wav"
    temp_path = container.settings.audio_dir / f"{make_id('stt')}_{original_name}"
    with temp_path.open("wb") as handle:
        shutil.copyfileobj(audio.file, handle)
    try:
        result = container.speech_service.transcribe(temp_path, language=language)
        return SpeechSttResponse(**result)
    except RuntimeError as exc:
        logger.warning("STT request failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)


@router.post("/speech/tts", response_model=SpeechTtsResponse)
async def speech_tts(request: Request, payload: SpeechTtsRequest) -> SpeechTtsResponse:
    try:
        result = _container(request).speech_service.synthesize(payload.text, payload.voice, payload.cache)
        return SpeechTtsResponse(
            audio_url=result["audio_url"],
            duration_ms=result["duration_ms"],
            cached=result["cached"],
        )
    except Exception as exc:
        logger.warning("TTS request failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/speech/cache/{filename}")
async def speech_cache(request: Request, filename: str) -> FileResponse:
    audio_path = _container(request).settings.audio_dir / filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(audio_path)


@router.get("/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    return _container(request).settings_service.get()


@router.put("/settings")
async def put_settings(request: Request, payload: SettingsPayload) -> dict[str, Any]:
    return _container(request).settings_service.update(payload.model_dump(exclude_unset=True))


@router.websocket("/events")
async def events_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    container: AppContainer = websocket.app.state.container
    queue = await container.event_bus.subscribe()
    try:
        await websocket.send_json({"type": "assistant_state_changed", "state": "idle", "emotion": "neutral", "animation_hint": "idle"})
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info("Event socket disconnected")
    finally:
        await container.event_bus.unsubscribe(queue)


@router.websocket("/assistant/stream")
async def assistant_stream_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    container: AppContainer = websocket.app.state.container
    session_context: dict[str, dict[str, Any]] = {}
    transcript_parts: dict[str, list[str]] = {}

    async def send_event(payload: dict[str, Any]) -> None:
        await websocket.send_json(payload)

    try:
        while True:
            payload = AssistantStreamMessage.model_validate(await websocket.receive_json())
            session_id = payload.session_id or "default"
            session_meta = session_context.setdefault(
                session_id,
                {
                    "conversation_id": payload.conversation_id,
                    "selected_date": payload.selected_date,
                    "notes_context": payload.notes_context,
                },
            )
            if payload.conversation_id:
                session_meta["conversation_id"] = payload.conversation_id
            if payload.selected_date is not None:
                session_meta["selected_date"] = payload.selected_date
            if payload.notes_context is not None:
                session_meta["notes_context"] = payload.notes_context

            if payload.type == "session_start":
                await send_event(
                    {
                        "type": "assistant_state_changed",
                        "state": "waiting",
                        "emotion": "neutral",
                        "animation_hint": "idle",
                        "session_id": session_id,
                    }
                )
                continue

            if payload.type == "context_update":
                await send_event(
                    {
                        "type": "assistant_state_changed",
                        "state": "listening" if payload.voice_mode else "waiting",
                        "emotion": "neutral",
                        "animation_hint": "listen" if payload.voice_mode else "idle",
                        "session_id": session_id,
                    }
                )
                continue

            if payload.type == "cancel_response":
                await send_event(
                    {
                        "type": "assistant_state_changed",
                        "state": "waiting",
                        "emotion": "neutral",
                        "animation_hint": "idle",
                        "session_id": session_id,
                    }
                )
                continue

            if payload.type == "session_stop":
                transcript_parts.pop(session_id, None)
                session_context.pop(session_id, None)
                container.repository.delete_assistant_session(session_id)
                await send_event(
                    {
                        "type": "assistant_state_changed",
                        "state": "idle",
                        "emotion": "neutral",
                        "animation_hint": "idle",
                        "session_id": session_id,
                    }
                )
                continue

            if payload.type == "text_turn":
                response = await container.assistant_orchestrator.stream_turn(
                    message=payload.message or "",
                    conversation_id=session_meta.get("conversation_id"),
                    session_id=session_id,
                    selected_date=session_meta.get("selected_date"),
                    voice_mode=payload.voice_mode,
                    notes_context=session_meta.get("notes_context"),
                    stream_emitter=send_event,
                )
                session_meta["conversation_id"] = response.conversation_id
                continue

            if payload.type == "voice_chunk":
                if not payload.audio_base64:
                    continue
                try:
                    transcript = container.speech_service.transcribe_bytes(
                        base64.b64decode(payload.audio_base64),
                        language=payload.language,
                    )
                    text = (transcript.get("text") or "").strip()
                    if text:
                        transcript_parts.setdefault(session_id, []).append(text)
                        await send_event(
                            {
                                "type": "transcript_partial",
                                "session_id": session_id,
                                "text": " ".join(transcript_parts.get(session_id, [])),
                            }
                        )
                except Exception as exc:
                    await send_event({"type": "error", "session_id": session_id, "detail": str(exc)})
                continue

            if payload.type == "voice_end":
                if payload.audio_base64:
                    try:
                        transcript = container.speech_service.transcribe_bytes(
                            base64.b64decode(payload.audio_base64),
                            language=payload.language,
                        )
                        text = (transcript.get("text") or "").strip()
                        if text:
                            transcript_parts.setdefault(session_id, []).append(text)
                    except Exception as exc:
                        await send_event({"type": "error", "session_id": session_id, "detail": str(exc)})
                        continue
                final_text = " ".join(transcript_parts.pop(session_id, [])).strip()
                await send_event(
                    {
                        "type": "transcript_final",
                        "session_id": session_id,
                        "text": final_text,
                    }
                )
                if final_text:
                    response = await container.assistant_orchestrator.stream_turn(
                        message=final_text,
                        conversation_id=session_meta.get("conversation_id"),
                        session_id=session_id,
                        selected_date=session_meta.get("selected_date"),
                        voice_mode=True,
                        notes_context=session_meta.get("notes_context"),
                        stream_emitter=send_event,
                    )
                    session_meta["conversation_id"] = response.conversation_id
                continue
    except WebSocketDisconnect:
        logger.info("Assistant stream socket disconnected")
