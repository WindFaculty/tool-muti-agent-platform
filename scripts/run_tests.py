from __future__ import annotations

import argparse
import json
import uuid

from app.core.auth import AuthContext
from app.core.config import get_settings
from app.core.container import build_container
from app.core.executor import execute_tool


def main() -> None:
    parser = argparse.ArgumentParser(description="Run project tests through the tool executor.")
    parser.add_argument("--path", default=".")
    parser.add_argument("--framework", default="auto")
    args = parser.parse_args()

    settings = get_settings()
    container = build_container(settings)
    request_id = str(uuid.uuid4())
    auth = AuthContext(service_token="internal", agent_id="tester", request_id=request_id)
    result = execute_tool(
        container=container,
        auth=auth,
        tool_name="test_runner",
        input_data={"path": args.path, "framework": args.framework, "extra_args": []},
        dry_run=False,
        request_id=request_id,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
