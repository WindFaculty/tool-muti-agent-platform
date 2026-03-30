from __future__ import annotations

from agents.contracts import PlanStep, TaskDefinition


class PlannerAgent:
    def build_plan(self, task: TaskDefinition) -> list[PlanStep]:
        goal_id = task.goal.get("id")
        if goal_id == "basic_3d_game":
            return [
                PlanStep(
                    id="prepare_scene",
                    title="Prepare a clean 3D demo scene",
                    kind="scene",
                    payload={
                        "mode": "create_or_load",
                        "scene_name": "AIDemoBasic3D",
                        "scene_path": "Assets/Scenes",
                        "template": "3d_basic",
                    },
                ),
                PlanStep(
                    id="create_scripts",
                    title="Create gameplay scripts",
                    kind="scripts",
                    payload={
                        "player_script_path": "Assets/AIDevDemo/Scripts/PlayerMover.cs",
                        "camera_script_path": "Assets/AIDevDemo/Scripts/FollowCamera.cs",
                    },
                ),
                PlanStep(
                    id="build_scene_objects",
                    title="Create and wire demo GameObjects",
                    kind="objects",
                    payload={},
                ),
                PlanStep(
                    id="verify_scene",
                    title="Verify scene structure and console health",
                    kind="verify",
                    payload={
                        "camera": "Main Camera",
                        "expected_objects": ["Main Camera", "Ground", "Player"],
                        "play_mode": True,
                        "screenshot_file_name": "ai-dev-demo.png",
                    },
                ),
            ]

        if goal_id == "scene_smoke_check":
            scene_path = task.goal.get("scene_path")
            if not scene_path:
                raise ValueError("scene_smoke_check requires goal.scene_path")

            return [
                PlanStep(
                    id="load_scene",
                    title="Load the requested scene for smoke verification",
                    kind="scene",
                    payload={
                        "mode": "load_existing",
                        "scene_asset_path": scene_path,
                    },
                ),
                PlanStep(
                    id="verify_scene",
                    title="Verify scene health and capture evidence",
                    kind="verify",
                    payload={
                        "camera": task.goal.get("camera", "Main Camera"),
                        "expected_objects": task.goal.get("expected_objects") or [],
                        "play_mode": bool(task.goal.get("play_mode", True)),
                        "screenshot_file_name": task.goal.get("screenshot_file_name", "ai-scene-smoke.png"),
                    },
                ),
            ]

        raise ValueError(f"Unsupported task goal: {goal_id}")
