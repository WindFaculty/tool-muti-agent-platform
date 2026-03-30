from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from app.core.events import EventBus
from app.core.ids import make_id
from app.core.time import iso_datetime, now_local
from app.db.repository import SQLiteRepository
from app.models.enums import AnimationHint, AssistantEmotion
from app.models.schemas import AssistantPlanPayload, ChatCard, ChatRequest, ChatResponse
from app.services.action_validator import ActionValidator, ValidatedTurn
from app.services.fast_response import FastResponseService
from app.services.llm import LlmService
from app.services.memory import MemoryService
from app.services.planning_engine import PlanningService
from app.services.settings import SettingsService
from app.services.speech import SpeechService
from app.services.router import RouterService
from app.core.logging import get_logger

StreamEmitter = Callable[[dict[str, Any]], Awaitable[None]]
logger = get_logger("assistant_orchestrator")


class AssistantOrchestrator:
    def __init__(
        self,
        *,
        repository: SQLiteRepository,
        event_bus: EventBus,
        action_validator: ActionValidator,
        router_service: RouterService,
        planning_service: PlanningService,
        fast_response_service: FastResponseService,
        memory_service: MemoryService,
        speech_service: SpeechService,
        settings_service: SettingsService,
        llm_service: LlmService,
    ) -> None:
        self._repository = repository
        self._event_bus = event_bus
        self._action_validator = action_validator
        self._router_service = router_service
        self._planning_service = planning_service
        self._fast_response_service = fast_response_service
        self._memory_service = memory_service
        self._speech_service = speech_service
        self._settings_service = settings_service
        self._llm_service = llm_service

    async def handle_chat(self, request: ChatRequest) -> ChatResponse:
        return await self._process_turn(
            message=request.message,
            conversation_id=request.conversation_id,
            session_id=request.session_id,
            selected_date=request.selected_date,
            include_voice=request.include_voice,
            voice_mode=request.voice_mode,
            notes_context=request.notes_context,
            stream_emitter=None,
        )

    async def stream_turn(
        self,
        *,
        message: str,
        conversation_id: str | None,
        session_id: str | None,
        selected_date: str | None,
        voice_mode: bool,
        notes_context: str | None,
        stream_emitter: StreamEmitter,
    ) -> ChatResponse:
        return await self._process_turn(
            message=message,
            conversation_id=conversation_id,
            session_id=session_id,
            selected_date=selected_date,
            include_voice=True,
            voice_mode=voice_mode,
            notes_context=notes_context,
            stream_emitter=stream_emitter,
        )

    async def _process_turn(
        self,
        *,
        message: str,
        conversation_id: str | None,
        session_id: str | None,
        selected_date: str | None,
        include_voice: bool,
        voice_mode: bool,
        notes_context: str | None,
        stream_emitter: StreamEmitter | None,
    ) -> ChatResponse:
        started = time.perf_counter()
        now = now_local()
        conversation_id = self._ensure_conversation(conversation_id, "voice" if voice_mode else "text", now)
        session_id = self._ensure_session(session_id, conversation_id, "voice" if voice_mode else "text", now)
        self._save_message(conversation_id, "user", message, None, None, {"notes_context": notes_context or ""})
        self._repository.touch_conversation(conversation_id, iso_datetime(now))
        if selected_date:
            self._repository.set_session_state("selected_date", selected_date)
        await self._publish_state("thinking", AssistantEmotion.THINKING.value, AnimationHint.THINK.value, stream_emitter)

        intent = self._action_validator.analyze(message, selected_date, notes_context)
        validated = self._action_validator.execute(intent)
        route = self._router_service.route_request(
            text=message,
            notes_context=notes_context,
            voice_mode=voice_mode,
        )
        self._update_session(
            session_id,
            conversation_id,
            mode="voice" if voice_mode else "text",
            voice_state="thinking",
            active_route=route.route,
            active_plan_id=None,
            metadata={"selected_date": selected_date, "notes_context": notes_context or ""},
            created_at=iso_datetime(now),
        )
        if stream_emitter is not None:
            await stream_emitter(
                {
                    "type": "route_selected",
                    "route": route.route,
                    "reason": route.reason,
                    "provider": route.provider,
                }
            )

        long_term_memory = self._memory_service.relevant_long_term_memory(f"{message}\n{notes_context or ''}")
        rolling_summary = self._memory_service.rolling_summary(conversation_id)

        final_text = validated.reply_text
        plan: AssistantPlanPayload | None = None
        fallback_used = False
        active_provider = route.provider
        token_usage: dict[str, Any] = defaultdict(int)
        plan_id: str | None = None
        error_text: str | None = None

        if route.route == "groq_fast":
            try:
                final_text, usage = self._fast_response_service.compose(
                    provider=self._settings_service.get()["model"].get("fast_provider", route.provider),
                    user_message=message,
                    intent=validated.kind,
                    factual_context=validated.factual_context,
                    spoken_brief=validated.reply_text,
                )
                active_provider = self._settings_service.get()["model"].get("fast_provider", route.provider)
                token_usage = self._merge_usage(token_usage, usage)
            except Exception as exc:
                fallback_used = True
                error_text = str(exc)
                try:
                    final_text, usage = self._fast_response_service.compose(
                        provider="gemini" if active_provider == "groq" else "groq",
                        user_message=message,
                        intent=validated.kind,
                        factual_context=validated.factual_context,
                        spoken_brief=validated.reply_text,
                    )
                    active_provider = "gemini" if active_provider == "groq" else "groq"
                    token_usage = self._merge_usage(token_usage, usage)
                except Exception:
                    final_text = self._fast_response_service.fallback_compose(
                        spoken_brief=validated.reply_text,
                        factual_context=validated.factual_context,
                    )

        elif route.route == "gemini_deep":
            plan_id = make_id("plan")
            try:
                plan, usage = self._planning_service.build_plan(
                    provider=self._settings_service.get()["model"].get("deep_provider", route.provider),
                    user_message=message,
                    intent=validated.kind,
                    selected_date=selected_date,
                    notes_context=notes_context,
                    factual_context=validated.factual_context,
                    rolling_summary=rolling_summary,
                    long_term_memory=long_term_memory,
                )
                active_provider = self._settings_service.get()["model"].get("deep_provider", route.provider)
                token_usage = self._merge_usage(token_usage, usage)
                final_text = plan.spoken_brief
            except Exception as exc:
                fallback_used = True
                error_text = str(exc)
                if not route.long_context:
                    try:
                        final_text, usage = self._fast_response_service.compose(
                            provider="groq",
                            user_message=message,
                            intent=validated.kind,
                            factual_context=validated.factual_context,
                            spoken_brief=validated.reply_text,
                        )
                        active_provider = "groq"
                        token_usage = self._merge_usage(token_usage, usage)
                    except Exception:
                        final_text = validated.reply_text
                else:
                    final_text = validated.reply_text

        else:
            plan_id = make_id("plan")
            try:
                plan, usage = self._planning_service.build_plan(
                    provider=self._settings_service.get()["model"].get("deep_provider", route.provider),
                    user_message=message,
                    intent=validated.kind,
                    selected_date=selected_date,
                    notes_context=notes_context,
                    factual_context=validated.factual_context,
                    rolling_summary=rolling_summary,
                    long_term_memory=long_term_memory,
                )
                active_provider = self._settings_service.get()["model"].get("deep_provider", route.provider)
                token_usage = self._merge_usage(token_usage, usage)
            except Exception as exc:
                fallback_used = True
                error_text = str(exc)
                plan = self._planning_service.fallback_plan(
                    user_message=message,
                    factual_context=validated.factual_context,
                    notes_context=notes_context,
                )

            try:
                final_text, usage = self._fast_response_service.compose(
                    provider=self._settings_service.get()["model"].get("fast_provider", "groq"),
                    user_message=message,
                    intent=validated.kind,
                    factual_context=validated.factual_context,
                    spoken_brief=plan.spoken_brief if plan else validated.reply_text,
                )
                active_provider = self._settings_service.get()["model"].get("fast_provider", "groq")
                token_usage = self._merge_usage(token_usage, usage)
            except Exception as exc:
                fallback_used = True
                error_text = error_text or str(exc)
                final_text = plan.spoken_brief if plan else validated.reply_text

        latency_ms = int((time.perf_counter() - started) * 1000)

        metadata = {
            "route": route.route,
            "provider": active_provider,
            "latency_ms": latency_ms,
            "token_usage": dict(token_usage),
            "fallback_used": fallback_used,
            "plan_id": plan_id,
        }
        self._save_message(
            conversation_id,
            "assistant",
            final_text,
            validated.emotion.value,
            validated.animation_hint.value,
            metadata,
        )
        self._repository.touch_conversation(conversation_id, iso_datetime(now_local()))
        self._memory_service.refresh_summary(conversation_id)
        stored_memory = self._memory_service.extract_and_store(
            conversation_id=conversation_id,
            user_message=message,
            assistant_reply=final_text,
            enabled=bool(self._settings_service.get().get("memory", {}).get("auto_extract", True)),
        )
        self._repository.add_route_log(
            {
                "id": make_id("route"),
                "conversation_id": conversation_id,
                "session_id": session_id,
                "route": route.route,
                "provider": active_provider,
                "model_name": self._llm_service.model_name(active_provider),
                "latency_ms": latency_ms,
                "token_usage_json": dict(token_usage),
                "fallback_used": fallback_used,
                "error_text": error_text,
                "created_at": iso_datetime(now_local()),
            }
        )

        for action in validated.task_actions:
            await self._event_bus.publish(
                {
                    "type": "task_updated",
                    "task_id": action.task_id,
                    "change": action.type,
                }
            )
            if stream_emitter is not None:
                await stream_emitter(
                    {
                        "type": "task_action_applied",
                        "action": action.model_dump(),
                    }
                )

        audio_url = None
        speak = bool(include_voice and self._settings_service.get()["voice"].get("speak_replies", True))
        if stream_emitter is not None:
            await self._publish_state("talking", validated.emotion.value, validated.animation_hint.value, stream_emitter)
            for chunk in self._chunk_text(final_text):
                await stream_emitter({"type": "assistant_chunk", "text": chunk})
            if speak:
                utterance_id = make_id("utt")
                await stream_emitter({"type": "speech_started", "utterance_id": utterance_id})
                try:
                    for item in self._speech_service.synthesize_sentences(
                        final_text,
                        self._settings_service.get()["voice"].get("tts_voice"),
                    ):
                        await stream_emitter(
                            {
                                "type": "tts_sentence_ready",
                                "text": item["text"],
                                "audio_url": item["audio_url"],
                                "duration_ms": item["duration_ms"],
                            }
                        )
                except Exception as exc:
                    logger.warning("Assistant stream TTS fallback triggered: %s", exc)
                    speak = False
                await stream_emitter({"type": "speech_finished", "utterance_id": utterance_id})
            await stream_emitter(
                {
                    "type": "assistant_final",
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "reply_text": final_text,
                    "route": route.route,
                    "provider": active_provider,
                    "latency_ms": latency_ms,
                    "token_usage": dict(token_usage),
                    "fallback_used": fallback_used,
                    "plan_id": plan_id,
                    "cards": [card.model_dump() for card in validated.cards],
                    "task_actions": [action.model_dump() for action in validated.task_actions],
                    "memory_items": stored_memory,
                }
            )
        elif speak:
            try:
                speech = self._speech_service.synthesize(
                    final_text,
                    self._settings_service.get()["voice"].get("tts_voice"),
                )
                audio_url = speech["audio_url"]
            except Exception as exc:
                logger.warning("Assistant reply TTS fallback triggered: %s", exc)
                speak = False

        await self._publish_state("idle", validated.emotion.value, validated.animation_hint.value, stream_emitter)
        self._update_session(
            session_id,
            conversation_id,
            mode="voice" if voice_mode else "text",
            voice_state="idle",
            active_route=route.route,
            active_plan_id=plan_id,
            metadata={
                "selected_date": selected_date,
                "notes_context": notes_context or "",
                "stored_memory": stored_memory,
            },
            created_at=iso_datetime(now),
        )

        return ChatResponse(
            conversation_id=conversation_id,
            reply_text=final_text,
            emotion=validated.emotion,
            animation_hint=validated.animation_hint,
            speak=speak,
            audio_url=audio_url,
            task_actions=validated.task_actions,
            cards=validated.cards + self._plan_cards(plan),
            route=route.route,
            provider=active_provider,
            latency_ms=latency_ms,
            token_usage=dict(token_usage),
            fallback_used=fallback_used,
            plan_id=plan_id,
        )

    async def _publish_state(
        self,
        state: str,
        emotion: str,
        animation_hint: str,
        stream_emitter: StreamEmitter | None,
    ) -> None:
        payload = {
            "type": "assistant_state_changed",
            "state": state,
            "emotion": emotion,
            "animation_hint": animation_hint,
        }
        await self._event_bus.publish(payload)
        if stream_emitter is not None:
            await stream_emitter(payload)

    def _ensure_conversation(self, conversation_id: str | None, mode: str, now: Any) -> str:
        if conversation_id and self._repository.get_conversation(conversation_id):
            return conversation_id
        new_id = make_id("conv")
        self._repository.create_conversation(
            {
                "id": new_id,
                "mode": mode,
                "created_at": iso_datetime(now),
                "updated_at": iso_datetime(now),
            }
        )
        return new_id

    def _ensure_session(self, session_id: str | None, conversation_id: str, mode: str, now: Any) -> str:
        existing = self._repository.get_assistant_session(session_id) if session_id else None
        if existing:
            return existing["id"]
        new_id = session_id or make_id("sess")
        self._update_session(
            new_id,
            conversation_id,
            mode=mode,
            voice_state="idle",
            active_route=None,
            active_plan_id=None,
            metadata={},
            created_at=iso_datetime(now),
        )
        return new_id

    def _update_session(
        self,
        session_id: str,
        conversation_id: str,
        *,
        mode: str,
        voice_state: str,
        active_route: str | None,
        active_plan_id: str | None,
        metadata: dict[str, Any],
        created_at: str,
    ) -> None:
        self._repository.upsert_assistant_session(
            {
                "id": session_id,
                "conversation_id": conversation_id,
                "mode": mode,
                "voice_state": voice_state,
                "active_route": active_route,
                "active_plan_id": active_plan_id,
                "metadata_json": metadata,
                "created_at": created_at,
                "updated_at": iso_datetime(now_local()),
            }
        )

    def _save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        emotion: str | None,
        animation_hint: str | None,
        metadata: dict[str, Any],
    ) -> None:
        self._repository.add_message(
            {
                "id": make_id("msg"),
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "emotion": emotion,
                "animation_hint": animation_hint,
                "metadata_json": json.dumps(metadata),
                "created_at": iso_datetime(now_local()),
            }
        )

    def _chunk_text(self, text: str, chunk_size: int = 60) -> list[str]:
        words = text.split()
        chunks = []
        current = []
        current_length = 0
        for word in words:
            current.append(word)
            current_length += len(word) + 1
            if current_length >= chunk_size or word.endswith((".", "!", "?")):
                chunks.append(" ".join(current))
                current = []
                current_length = 0
        if current:
            chunks.append(" ".join(current))
        return chunks or [text]

    def _merge_usage(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        merged = dict(left)
        for key, value in right.items():
            if isinstance(value, int):
                merged[key] = int(merged.get(key, 0)) + value
            else:
                merged[key] = value
        return merged

    def _plan_cards(self, plan: AssistantPlanPayload | None) -> list[ChatCard]:
        if plan is None:
            return []
        return [
            ChatCard(type="planner_output", payload=plan.model_dump())
        ]
