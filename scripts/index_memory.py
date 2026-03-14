from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.core.container import build_container


def main() -> None:
    parser = argparse.ArgumentParser(description="Index project knowledge into AI Dev OS.")
    parser.add_argument("--project-id", required=True)
    args = parser.parse_args()

    settings = get_settings()
    container = build_container(settings)
    print(json.dumps(container.knowledge_service.index_project(args.project_id)))


if __name__ == "__main__":
    main()
