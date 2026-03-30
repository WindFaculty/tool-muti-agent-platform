from __future__ import annotations

import asyncio
import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent

for child in ("agents", "planner", "executor", "memory", "tools", "workflows", "unity-interface"):
    sys.path.append(str(ROOT / child))

from autonomous_loop import AutonomousUnityWorkflow
from workflow_report import build_workflow_report, format_workflow_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an MCP-driven Unity automation task.")
    parser.add_argument(
        "--task",
        default=str(ROOT / "tasks" / "demo_simple_3d_game.json"),
        help="Path to the task definition JSON file.",
    )
    parser.add_argument(
        "--summary-out",
        default=str(ROOT / "logs" / "last-summary.json"),
        help="Path to write the full workflow summary JSON.",
    )
    parser.add_argument(
        "--report-out",
        default=str(ROOT / "logs" / "last-report.json"),
        help="Path to write the concise workflow report JSON.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    workflow = AutonomousUnityWorkflow(ROOT)
    task = workflow.load_task(Path(args.task))
    summary = await workflow.run(REPO_ROOT, task)
    report = build_workflow_report(summary)

    summary_path = Path(args.summary_out)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report_path = Path(args.report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(format_workflow_report(report))
    print(f"\nFull summary written to {summary_path}")
    print(f"Concise report written to {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
