from __future__ import annotations


def test_assistant_stream_text_turn_emits_route_and_final(client) -> None:
    with client.websocket_connect("/v1/assistant/stream") as websocket:
        websocket.send_json(
            {
                "type": "session_start",
                "session_id": "sess_test",
                "selected_date": None,
                "voice_mode": False,
            }
        )
        first = websocket.receive_json()
        assert first["type"] == "assistant_state_changed"

        websocket.send_json(
            {
                "type": "text_turn",
                "session_id": "sess_test",
                "conversation_id": None,
                "message": "Hom nay toi co gi?",
                "voice_mode": False,
            }
        )

        seen_types: list[str] = []
        final_payload = None
        for _ in range(8):
            event = websocket.receive_json()
            seen_types.append(event["type"])
            if event["type"] == "assistant_final":
                final_payload = event
                break

        assert "route_selected" in seen_types
        assert final_payload is not None
        assert final_payload["reply_text"]
        assert final_payload["route"] in {"groq_fast", "gemini_deep", "hybrid_plan_then_groq"}


def test_assistant_stream_voice_end_emits_transcript_and_final(client) -> None:
    client.app.state.container.speech_service.transcribe_bytes = lambda wav_bytes, language=None: {
        "text": "Them task demo ngay mai",
        "language": language or "vi",
        "confidence": 1.0,
    }

    with client.websocket_connect("/v1/assistant/stream") as websocket:
        websocket.send_json(
            {
                "type": "session_start",
                "session_id": "sess_voice",
                "selected_date": None,
                "voice_mode": True,
            }
        )
        websocket.receive_json()

        websocket.send_json(
            {
                "type": "voice_end",
                "session_id": "sess_voice",
                "conversation_id": None,
                "voice_mode": True,
                "audio_base64": "c3R1Yi13YXY=",
            }
        )

        seen_types: list[str] = []
        final_payload = None
        for _ in range(10):
            event = websocket.receive_json()
            seen_types.append(event["type"])
            if event["type"] == "assistant_final":
                final_payload = event
                break

        assert "transcript_final" in seen_types
        assert final_payload is not None
        assert final_payload["reply_text"]


def test_assistant_stream_text_turn_still_finishes_when_tts_errors_unexpectedly(client) -> None:
    client.app.state.container.speech_service.synthesize_sentences = (
        lambda text, voice=None, cache=True: (_ for _ in ()).throw(ValueError("chattts load mismatch"))
    )

    with client.websocket_connect("/v1/assistant/stream") as websocket:
        websocket.send_json(
            {
                "type": "session_start",
                "session_id": "sess_tts_fallback",
                "selected_date": None,
                "voice_mode": False,
            }
        )
        websocket.receive_json()

        websocket.send_json(
            {
                "type": "text_turn",
                "session_id": "sess_tts_fallback",
                "conversation_id": None,
                "message": "Them task fallback check ngay mai",
                "voice_mode": False,
            }
        )

        seen_types: list[str] = []
        final_payload = None
        for _ in range(12):
            event = websocket.receive_json()
            seen_types.append(event["type"])
            if event["type"] == "assistant_final":
                final_payload = event
                break

        assert "speech_started" in seen_types
        assert "speech_finished" in seen_types
        assert final_payload is not None
        assert final_payload["reply_text"]


def test_assistant_stream_voice_chunk_emits_error_when_transcription_fails(client) -> None:
    client.app.state.container.speech_service.transcribe_bytes = (
        lambda wav_bytes, language=None: (_ for _ in ()).throw(RuntimeError("stt offline"))
    )

    with client.websocket_connect("/v1/assistant/stream") as websocket:
        websocket.send_json(
            {
                "type": "session_start",
                "session_id": "sess_voice_error",
                "selected_date": None,
                "voice_mode": True,
            }
        )
        websocket.receive_json()

        websocket.send_json(
            {
                "type": "voice_chunk",
                "session_id": "sess_voice_error",
                "conversation_id": None,
                "voice_mode": True,
                "audio_base64": "c3R1Yi13YXY=",
            }
        )

        event = websocket.receive_json()
        assert event["type"] == "error"
        assert event["session_id"] == "sess_voice_error"
        assert "stt offline" in event["detail"]
