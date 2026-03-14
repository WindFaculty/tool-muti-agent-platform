from __future__ import annotations

import argparse
import json
import uuid

from app.core.auth import AuthContext
from app.core.config import get_settings
from app.core.container import build_container
from app.core.executor import execute_tool


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local deployment build.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--context-path", default=".")
    parser.add_argument("--tag", default="local/dev-os")
    args = parser.parse_args()

    settings = get_settings()
    container = build_container(settings)
    deployment_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    auth = AuthContext(service_token="internal", agent_id="devops", request_id=request_id)
    result = execute_tool(
        container=container,
        auth=auth,
        tool_name="docker_build",
        input_data={"context_path": args.context_path, "tag": args.tag},
        dry_run=False,
        request_id=request_id,
    )
    container.repository.create_deployment(
        deployment_id=deployment_id,
        project_id=args.project_id,
        run_id=None,
        target="local-docker",
        status=result["status"],
        log_path=None,
    )
    print(json.dumps({"deployment_id": deployment_id, "result": result}))


if __name__ == "__main__":
    main()
