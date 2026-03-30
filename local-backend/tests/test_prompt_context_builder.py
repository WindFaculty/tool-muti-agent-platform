from __future__ import annotations

from app.core.config import Settings
from app.services.prompt_context import PromptContextBuilderService


def _settings(tmp_path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        db_path=tmp_path / "data" / "app.db",
        audio_dir=tmp_path / "data" / "audio",
        cache_dir=tmp_path / "data" / "cache",
        log_dir=tmp_path / "data" / "logs",
        **overrides,
    )


def test_fast_payload_omits_raw_context_and_caps_tasks(tmp_path) -> None:
    builder = PromptContextBuilderService(_settings(tmp_path, fast_context_task_limit=3))

    factual_context = {
        "summary": {
            "text": "Ban co 5 viec hom nay va 2 viec uu tien cao.",
            "task_count": 5,
            "high_priority_count": 2,
            "items": [
                {"title": "A", "priority": "high", "scheduled_date": "2026-03-19", "status": "planned"},
                {"title": "B", "priority": "medium", "scheduled_date": "2026-03-19", "status": "planned"},
                {"title": "C", "priority": "medium", "scheduled_date": "2026-03-19", "status": "planned"},
                {"title": "D", "priority": "low", "scheduled_date": "2026-03-19", "status": "planned"},
            ],
            "suggestions": ["Lam viec A truoc.", "Khoa focus block 09:00.", "Bo qua muc nay"],
        },
        "tasks": [
            {"title": "A", "priority": "high", "scheduled_date": "2026-03-19", "status": "planned", "description": "x"},
            {"title": "B", "priority": "medium", "scheduled_date": "2026-03-19", "status": "planned"},
            {"title": "C", "priority": "medium", "scheduled_date": "2026-03-19", "status": "planned"},
            {"title": "D", "priority": "low", "scheduled_date": "2026-03-19", "status": "planned"},
        ],
    }

    payload = builder.build_fast_payload(
        user_message="Hom nay toi co gi?",
        intent="lookup_day",
        factual_context=factual_context,
        spoken_brief="Ban co 5 viec.",
    )

    assert set(payload) == {"msg", "intent", "facts", "brief"}
    assert "factual_context" not in payload
    assert "rolling_summary" not in payload
    assert "long_term_memory" not in payload
    assert payload["facts"].startswith("sum:")
    assert "top=" in payload["facts"]
    assert payload["facts"].count(";") <= 2
    assert "description" not in payload["facts"]


def test_plan_payload_enforces_notes_summary_and_memory_caps(tmp_path) -> None:
    builder = PromptContextBuilderService(
        _settings(
            tmp_path,
            deep_context_task_limit=2,
            notes_context_word_limit=6,
            rolling_summary_line_limit=2,
            long_term_memory_limit=2,
        )
    )

    factual_context = {
        "daily": {
            "text": "Hom nay co nhieu viec quan trong can xu ly som.",
            "items": [
                {"title": "A", "priority": "high", "scheduled_date": "2026-03-19", "status": "planned"},
                {"title": "B", "priority": "medium", "scheduled_date": "2026-03-19", "status": "planned"},
                {"title": "C", "priority": "low", "scheduled_date": "2026-03-19", "status": "planned"},
            ],
        },
        "weekly": {"text": "Tuan nay co 2 deadline.", "overloaded_days": [{"date": "2026-03-20", "task_count": 4}]},
        "tasks": [
            {"title": "A", "priority": "high", "scheduled_date": "2026-03-19", "status": "planned"},
            {"title": "B", "priority": "medium", "scheduled_date": "2026-03-19", "status": "planned"},
            {"title": "C", "priority": "low", "scheduled_date": "2026-03-19", "status": "planned"},
        ],
    }

    payload = builder.build_plan_payload(
        user_message="Lap ke hoach cho toi",
        intent="planning",
        selected_date="2026-03-19",
        notes_context="mot hai ba bon nam sau bay tam chin",
        factual_context=factual_context,
        rolling_summary="User: dong 1\nAssistant: dong 2\nUser: dong 3",
        long_term_memory=[
            {"category": "goal", "content": "hoan thanh backend truoc thu sau", "metadata": {"x": 1}},
            {"category": "routine", "content": "thuong hop nhom vao sang thu hai"},
            {"category": "project", "content": "dang lam UI va websocket"},
        ],
    )

    assert payload["date"] == "2026-03-19"
    assert len(payload["notes"].split()) == 6
    assert payload["roll"].count("||") == 1
    assert len(payload["mem"]) == 2
    assert all(isinstance(item, str) for item in payload["mem"])
    assert len(payload["facts"]["day"]["items"]) == 2
    assert len(payload["facts"]["top"]) == 2
    assert "notes_context" not in payload
    assert "rolling_summary" not in payload
    assert "long_term_memory" not in payload
