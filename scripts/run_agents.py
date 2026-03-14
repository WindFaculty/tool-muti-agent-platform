from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.core.container import build_container


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI Dev OS agent utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    worker_parser = subparsers.add_parser("worker", help="Inspect the worker configuration")
    worker_parser.add_argument("--json", action="store_true", help="Return JSON output")
    args = parser.parse_args()

    settings = get_settings()
    container = build_container(settings)
    payload = {
        "agents": sorted(container.agent_factory._agents.keys()),
        "workflows": [workflow.workflow_id for workflow in container.workflow_loader.list_workflows()],
    }
    if args.json:
        print(json.dumps(payload))
    else:
        print("Agents:", ", ".join(payload["agents"]))
        print("Workflows:", ", ".join(payload["workflows"]))


if __name__ == "__main__":
    main()
