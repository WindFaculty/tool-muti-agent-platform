from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from agents.contracts import TaskDefinition
from planner.planner_agent import PlannerAgent


class TaskLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = PlannerAgent()
        self.task_dir = ROOT / "tasks"

    def test_all_task_definitions_build_supported_plans(self) -> None:
        task_paths = sorted(self.task_dir.glob("*.json"))

        self.assertGreaterEqual(len(task_paths), 5)

        for task_path in task_paths:
            with self.subTest(task=task_path.name):
                payload = json.loads(task_path.read_text(encoding="utf-8"))
                task = TaskDefinition(
                    id=payload["id"],
                    title=payload["title"],
                    prompt=payload["prompt"],
                    goal=payload["goal"],
                )

                plan = self.agent.build_plan(task)

                self.assertGreater(len(plan), 0)
                self.assertEqual(plan[0].kind, "scene")
                self.assertIn(plan[-1].kind, {"verify", "objects"})

    def test_scene_smoke_tasks_reference_existing_unity_scenes(self) -> None:
        for task_path in sorted(self.task_dir.glob("*.json")):
            payload = json.loads(task_path.read_text(encoding="utf-8"))
            if payload["goal"].get("id") != "scene_smoke_check":
                continue

            with self.subTest(task=task_path.name):
                scene_path = payload["goal"]["scene_path"]
                unity_scene_path = REPO_ROOT / "unity-client" / scene_path

                self.assertTrue(unity_scene_path.exists(), f"Missing scene for task {task_path.name}: {scene_path}")


if __name__ == "__main__":
    unittest.main()
