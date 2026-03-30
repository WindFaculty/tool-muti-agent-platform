from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from agents.contracts import TaskDefinition
from planner.planner_agent import PlannerAgent


class PlannerAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = PlannerAgent()

    def test_build_plan_for_scene_smoke_check(self) -> None:
        task = TaskDefinition(
            id="scene_smoke",
            title="Scene smoke",
            prompt="Verify scene",
            goal={
                "id": "scene_smoke_check",
                "scene_path": "Assets/Scenes/AIDemoBasic3D.unity",
                "camera": "Main Camera",
                "expected_objects": ["Player"],
                "play_mode": True,
            },
        )

        plan = self.agent.build_plan(task)

        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0].kind, "scene")
        self.assertEqual(plan[0].payload["mode"], "load_existing")
        self.assertEqual(plan[1].kind, "verify")
        self.assertEqual(plan[1].payload["expected_objects"], ["Player"])


if __name__ == "__main__":
    unittest.main()
