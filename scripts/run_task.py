from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.core.container import build_container


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or run AI Dev OS tasks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a task")
    create_parser.add_argument("--project-id", required=True)
    create_parser.add_argument("--title", required=True)
    create_parser.add_argument("--description", default="")
    create_parser.add_argument("--requirements", default="")
    create_parser.add_argument("--expected-output", default="")
    create_parser.add_argument("--priority", default="medium")
    create_parser.add_argument("--workflow-id", default="feature-development")

    run_parser = subparsers.add_parser("run", help="Run an existing task")
    run_parser.add_argument("--task-id", required=True)

    args = parser.parse_args()
    settings = get_settings()
    container = build_container(settings)

    if args.command == "create":
        if not container.project_service.get_project(args.project_id):
            container.project_service.create_project(
                project_id=args.project_id,
                name=args.project_id,
            )
        task = container.task_service.create_task(
            project_id=args.project_id,
            title=args.title,
            description_md=args.description,
            requirements_md=args.requirements,
            expected_output_md=args.expected_output,
            priority=args.priority,
            workflow_id=args.workflow_id,
        )
        print(json.dumps(task.model_dump()))
        return

    result = container.orchestrator.run_task(args.task_id)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
