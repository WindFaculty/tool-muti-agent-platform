from __future__ import annotations

from token_benchmark_support import run_token_benchmark


def test_token_compaction_benchmark_meets_targets(tmp_path) -> None:
    summary = run_token_benchmark(tmp_path)

    for fixture in summary["fixtures"]:
        assert fixture["fallback_used"] is False
        assert fixture["route"] == fixture["baseline_route"]

    assert summary["fast_average_reduction_pct"] >= 60.0
    assert summary["deep_average_reduction_pct"] >= 40.0
    assert summary["average_reduction_pct"] >= 50.0
