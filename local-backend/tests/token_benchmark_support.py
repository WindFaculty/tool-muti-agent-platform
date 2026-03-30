from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.main import create_app

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class _Reply:
    def __init__(self, text: str, token_usage: dict[str, int]) -> None:
        self.text = text
        self.token_usage = token_usage


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _fake_complete(*, provider, system_prompt, user_prompt, json_output=False, temperature=None):
    token_usage = {
        "input_tokens": _estimate_tokens(system_prompt) + _estimate_tokens(user_prompt),
        "output_tokens": 24,
    }
    if json_output:
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
    return _Reply("Tra loi ngan gon.", token_usage)


def run_token_benchmark(tmp_path: Path) -> dict[str, Any]:
    settings = Settings(
        _env_file=None,
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        db_path=tmp_path / "data" / "benchmark.db",
        audio_dir=tmp_path / "data" / "audio",
        cache_dir=tmp_path / "data" / "cache",
        log_dir=tmp_path / "data" / "logs",
        llm_provider="hybrid",
        routing_mode="auto",
        fast_provider="groq",
        deep_provider="gemini",
        groq_api_key="test-key",
        gemini_api_key="test-key",
        stt_provider="whisper_cpp",
        whisper_command=None,
        piper_command=None,
        tts_provider="piper",
        reminder_poll_seconds=1,
    )
    app = create_app(settings)

    cases = json.loads((FIXTURES_DIR / "token_benchmark_cases.json").read_text(encoding="utf-8"))
    baseline = json.loads((FIXTURES_DIR / "token_baseline_pre_compaction.json").read_text(encoding="utf-8"))
    baseline_by_name = {item["name"]: item for item in baseline["fixtures"]}

    fixtures: list[dict[str, Any]] = []
    with TestClient(app) as client:
        container = client.app.state.container
        container.llm_service.provider_available = lambda provider: True
        container.llm_service.complete = _fake_complete

        for case in cases:
            prepare_task = case.get("prepare_task")
            if prepare_task:
                client.post("/v1/tasks", json=prepare_task)
            response = client.post("/v1/chat", json=case["request"])
            assert response.status_code == 200, response.text
            payload = response.json()
            baseline_item = baseline_by_name[case["name"]]
            current_input = payload.get("token_usage", {}).get("input_tokens", 0)
            baseline_input = baseline_item["input_tokens"]
            reduction_pct = round((baseline_input - current_input) * 100 / baseline_input, 2)
            fixtures.append(
                {
                    "name": case["name"],
                    "route": payload.get("route"),
                    "baseline_route": baseline_item["route"],
                    "provider": payload.get("provider"),
                    "input_tokens": current_input,
                    "baseline_input_tokens": baseline_input,
                    "reduction_pct": reduction_pct,
                    "fallback_used": payload.get("fallback_used", False),
                }
            )

    total_input_tokens = sum(item["input_tokens"] for item in fixtures)
    reductions = [item["reduction_pct"] for item in fixtures]
    fast = [item for item in fixtures if item["route"] == "groq_fast"]
    deep = [item for item in fixtures if item["route"] != "groq_fast"]
    return {
        "fixtures": fixtures,
        "total_input_tokens": total_input_tokens,
        "average_input_tokens": round(total_input_tokens / len(fixtures), 2),
        "average_reduction_pct": round(sum(reductions) / len(reductions), 2),
        "fast_average_reduction_pct": round(sum(item["reduction_pct"] for item in fast) / len(fast), 2),
        "deep_average_reduction_pct": round(sum(item["reduction_pct"] for item in deep) / len(deep), 2),
    }
