from __future__ import annotations

import anyio
from typing import Any

from agents.contracts import ExecutionRecord, PlanStep
from mcp_client import UnityMcpClient


PLAYER_MOVER_SCRIPT = """using UnityEngine;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

public sealed class PlayerMover : MonoBehaviour
{
    [SerializeField] private float moveSpeed = 6f;

    private Rigidbody _rigidbody = null!;
    private Vector3 _input;

    private void Awake()
    {
        _rigidbody = GetComponent<Rigidbody>();
        if (_rigidbody == null)
        {
            _rigidbody = gameObject.AddComponent<Rigidbody>();
        }

        _rigidbody.constraints = RigidbodyConstraints.FreezeRotation;
    }

    private void Update()
    {
#if ENABLE_INPUT_SYSTEM
        Keyboard keyboard = Keyboard.current;
        if (keyboard == null)
        {
            _input = Vector3.zero;
            return;
        }

        Vector2 move = Vector2.zero;

        if (keyboard.aKey.isPressed || keyboard.leftArrowKey.isPressed)
        {
            move.x -= 1f;
        }

        if (keyboard.dKey.isPressed || keyboard.rightArrowKey.isPressed)
        {
            move.x += 1f;
        }

        if (keyboard.sKey.isPressed || keyboard.downArrowKey.isPressed)
        {
            move.y -= 1f;
        }

        if (keyboard.wKey.isPressed || keyboard.upArrowKey.isPressed)
        {
            move.y += 1f;
        }

        if (move.sqrMagnitude > 1f)
        {
            move.Normalize();
        }

        _input = new Vector3(move.x, 0f, move.y);
#else
        _input = new Vector3(Input.GetAxisRaw("Horizontal"), 0f, Input.GetAxisRaw("Vertical")).normalized;
#endif
    }

    private void FixedUpdate()
    {
        Vector3 delta = _input * (moveSpeed * Time.fixedDeltaTime);
        _rigidbody.MovePosition(_rigidbody.position + delta);
    }
}
"""


FOLLOW_CAMERA_SCRIPT = """using UnityEngine;

public sealed class FollowCamera : MonoBehaviour
{
    [SerializeField] private string targetTag = "Player";
    [SerializeField] private Vector3 offset = new Vector3(0f, 4.5f, -7f);
    [SerializeField] private float followSpeed = 8f;

    private Transform _target;

    private void LateUpdate()
    {
        if (_target == null)
        {
            GameObject targetObject = GameObject.FindGameObjectWithTag(targetTag);
            if (targetObject != null)
            {
                _target = targetObject.transform;
            }
        }

        if (_target == null)
        {
            return;
        }

        Vector3 desiredPosition = _target.position + offset;
        transform.position = Vector3.Lerp(transform.position, desiredPosition, followSpeed * Time.deltaTime);
        transform.LookAt(_target.position + Vector3.up * 0.75f);
    }
}
"""


class ExecutorAgent:
    async def execute(self, client: UnityMcpClient, step: PlanStep) -> ExecutionRecord:
        if step.kind == "scene":
            mode = step.payload.get("mode", "create_or_load")
            if mode == "create_or_load":
                return await self._prepare_scene(client, step)
            if mode == "load_existing":
                return await self._load_existing_scene(client, step.id, str(step.payload["scene_asset_path"]))
            raise ValueError(f"Unsupported scene step mode: {mode}")

        if step.kind == "scripts":
            player_result = await self._ensure_script(client, step.payload["player_script_path"], PLAYER_MOVER_SCRIPT)
            camera_result = await self._ensure_script(client, step.payload["camera_script_path"], FOLLOW_CAMERA_SCRIPT)
            return ExecutionRecord(
                step_id=step.id,
                status="completed",
                details={"player_script": player_result, "camera_script": camera_result},
            )

        if step.kind == "objects":
            hierarchy_before = await client.get_scene_hierarchy()
            roots_before = self._root_items(hierarchy_before)

            cleanup_commands: list[dict[str, Any]] = []
            cleanup_commands.extend(self._delete_duplicates(roots_before, "Ground"))
            cleanup_commands.extend(self._delete_duplicates(roots_before, "Player"))

            cleanup_result = None
            if cleanup_commands:
                cleanup_result = await client.batch_execute(cleanup_commands)

            hierarchy_after_cleanup = await client.get_scene_hierarchy()
            roots = self._root_items(hierarchy_after_cleanup)

            primary_ground = self._first_item(roots, "Ground")
            primary_player = self._first_item(roots, "Player")
            main_camera = self._first_item(roots, "Main Camera")

            sync_commands: list[dict[str, Any]] = []
            sync_commands.append(
                self._gameobject_command(
                    target=primary_ground.get("instanceID") if primary_ground else None,
                    name="Ground",
                    primitive_type="Plane",
                    position=[0, 0, 0],
                    scale=[3, 1, 3],
                )
            )
            sync_commands.append(
                self._gameobject_command(
                    target=primary_player.get("instanceID") if primary_player else None,
                    name="Player",
                    primitive_type="Cube",
                    position=[0, 1, 0],
                    scale=[1, 1, 1],
                    tag="Player",
                    create_only_when_missing=True,
                )
            )
            if main_camera is not None:
                sync_commands.append(
                    {
                        "tool": "manage_gameobject",
                        "params": {
                            "action": "modify",
                            "target": main_camera["instanceID"],
                            "searchMethod": "by_id",
                            "position": [0, 5, -8],
                            "rotation": [20, 0, 0],
                        },
                    }
                )

            sync_result = await client.batch_execute(sync_commands)

            hierarchy_after_sync = await client.get_scene_hierarchy()
            roots_after_sync = self._root_items(hierarchy_after_sync)
            player_after_sync = self._first_item(roots_after_sync, "Player")
            camera_after_sync = self._first_item(roots_after_sync, "Main Camera")

            wire_commands: list[dict[str, Any]] = []
            if player_after_sync is not None and not self._has_component(player_after_sync, "Rigidbody"):
                wire_commands.append(self._add_component_command(player_after_sync["instanceID"], "Rigidbody"))
            if player_after_sync is not None and not self._has_component(player_after_sync, "PlayerMover"):
                wire_commands.append(self._add_component_command(player_after_sync["instanceID"], "PlayerMover"))
            if camera_after_sync is not None and not self._has_component(camera_after_sync, "FollowCamera"):
                wire_commands.append(self._add_component_command(camera_after_sync["instanceID"], "FollowCamera"))

            wire_result = None
            if wire_commands:
                wire_result = await client.batch_execute(wire_commands)

            return ExecutionRecord(
                step_id=step.id,
                status="completed",
                details={
                    "hierarchy_before": hierarchy_before,
                    "cleanup_batch": cleanup_result,
                    "sync_batch": sync_result,
                    "wiring_batch": wire_result,
                    "hierarchy_after": await client.get_scene_hierarchy(),
                },
            )

        if step.kind == "verify":
            camera_name = str(step.payload.get("camera", "Main Camera"))
            expected_objects = [str(item) for item in (step.payload.get("expected_objects") or [])]
            should_toggle_play_mode = bool(step.payload.get("play_mode", True))
            screenshot_file_name = str(step.payload.get("screenshot_file_name", "ai-dev-demo.png"))

            hierarchy = await client.get_scene_hierarchy()
            expected_object_results: dict[str, Any] = {}
            for object_name in expected_objects:
                expected_object_results[object_name] = await client.find_gameobjects(object_name)

            play_result = None
            stop_result = None
            if should_toggle_play_mode:
                play_result = await self._call_with_retry(client.play)
                await anyio.sleep(2)
                stop_result = await self._call_with_retry(client.stop)

            console_result = await client.read_console(types=["error", "warning", "log"], count=50, format_name="json")
            screenshot_result = await client.call_tool(
                "manage_camera",
                {
                    "action": "screenshot",
                    "camera": camera_name,
                    "include_image": False,
                    "screenshot_file_name": screenshot_file_name,
                },
            )
            return ExecutionRecord(
                step_id=step.id,
                status="completed",
                details={
                    "hierarchy": hierarchy,
                    "expected_objects": expected_object_results,
                    "play": play_result,
                    "stop": stop_result,
                    "console": console_result,
                    "screenshot": screenshot_result,
                },
            )

        raise ValueError(f"Unsupported step kind: {step.kind}")

    async def _ensure_script(self, client: UnityMcpClient, path: str, contents: str) -> dict[str, Any]:
        create_result = await client.create_script(path, contents)
        if self._looks_successful(create_result):
            return {"mode": "created", "result": create_result}

        if "already exists" in self._result_text(create_result).lower():
            update_result = await client.update_script(path, contents)
            return {"mode": "updated", "create_attempt": create_result, "result": update_result}

        return {"mode": "create_failed", "result": create_result}

    async def _prepare_scene(self, client: UnityMcpClient, step: PlanStep) -> ExecutionRecord:
        scene_name = step.payload["scene_name"]
        scene_folder = step.payload["scene_path"].rstrip("/")
        scene_asset_path = f"{scene_folder}/{scene_name}.unity"

        create_result = await client.create_scene(
            name=scene_name,
            path=step.payload["scene_path"],
            template=step.payload["template"],
        )
        if self._looks_successful(create_result):
            return ExecutionRecord(step_id=step.id, status="completed", details={"create_scene": create_result})

        if "already exists" in self._result_text(create_result).lower():
            load_record = await self._load_existing_scene(client, step.id, scene_asset_path)
            load_record.details["create_scene"] = create_result
            return load_record

        return ExecutionRecord(step_id=step.id, status="failed", details={"create_scene": create_result})

    async def _load_existing_scene(self, client: UnityMcpClient, step_id: str, scene_asset_path: str) -> ExecutionRecord:
        active_scene = await client.get_active_scene()
        active_scene_data = (active_scene.get("structured_content") or {}).get("data") or {}
        if active_scene_data.get("path") == scene_asset_path:
            return ExecutionRecord(step_id=step_id, status="completed", details={"active_scene": active_scene})

        load_result = await self._call_with_retry(lambda: client.load_scene(scene_asset_path))
        if self._looks_successful(load_result):
            return ExecutionRecord(step_id=step_id, status="completed", details={"load_existing_scene": load_result})

        refreshed_active_scene = await client.get_active_scene()
        refreshed_active_data = (refreshed_active_scene.get("structured_content") or {}).get("data") or {}
        if refreshed_active_data.get("path") == scene_asset_path:
            return ExecutionRecord(
                step_id=step_id,
                status="completed",
                details={"load_existing_scene": load_result, "active_scene": refreshed_active_scene},
            )

        return ExecutionRecord(
            step_id=step_id,
            status="failed",
            details={"load_existing_scene": load_result, "active_scene": refreshed_active_scene},
        )

    async def _call_with_retry(self, operation, *, attempts: int = 4, delay_seconds: float = 0.5) -> dict[str, Any]:
        last_result: dict[str, Any] | None = None
        for attempt in range(attempts):
            last_result = await operation()
            if not self._should_retry_result(last_result) or attempt == attempts - 1:
                return last_result
            await anyio.sleep(delay_seconds)
        return last_result or {}

    @staticmethod
    def _looks_successful(result: dict[str, Any] | None) -> bool:
        if not result:
            return False
        if result.get("is_error"):
            return False
        structured = result.get("structured_content") or {}
        return bool(structured.get("success"))

    @staticmethod
    def _result_text(result: dict[str, Any] | None) -> str:
        if not result:
            return ""
        structured = result.get("structured_content") or {}
        parts = [structured.get("message"), structured.get("code"), structured.get("error")]
        return " ".join(str(part) for part in parts if part)

    @classmethod
    def _should_retry_result(cls, result: dict[str, Any] | None) -> bool:
        if not result:
            return False
        if result.get("is_error"):
            return True

        structured = result.get("structured_content") or {}
        data = structured.get("data") or {}
        message = cls._result_text(result).lower()

        if data.get("reason") == "reloading":
            return True

        return "please retry" in message or "hint='retry'" in message or 'hint="retry"' in message

    @staticmethod
    def _root_items(hierarchy: dict[str, Any]) -> list[dict[str, Any]]:
        structured = hierarchy.get("structured_content") or {}
        data = structured.get("data") or {}
        items = data.get("items") or []
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _first_item(items: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
        for item in items:
            if item.get("name") == name:
                return item
        return None

    def _delete_duplicates(self, items: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
        matches = [item for item in items if item.get("name") == name]
        if len(matches) <= 1:
            return []

        commands: list[dict[str, Any]] = []
        for duplicate in matches[1:]:
            instance_id = duplicate.get("instanceID")
            if instance_id is None:
                continue
            commands.append(
                {
                    "tool": "manage_gameobject",
                    "params": {
                        "action": "delete",
                        "target": instance_id,
                        "searchMethod": "by_id",
                    },
                }
            )
        return commands

    @staticmethod
    def _gameobject_command(
        *,
        target: int | None,
        name: str,
        primitive_type: str,
        position: list[float],
        scale: list[float],
        tag: str | None = None,
        create_only_when_missing: bool = False,
    ) -> dict[str, Any]:
        if target is None:
            params: dict[str, Any] = {
                "action": "create",
                "name": name,
                "primitiveType": primitive_type,
                "position": position,
                "scale": scale,
            }
            if tag is not None:
                params["tag"] = tag
            return {"tool": "manage_gameobject", "params": params}

        if create_only_when_missing:
            return {
                "tool": "manage_gameobject",
                "params": {
                    "action": "modify",
                    "target": target,
                    "searchMethod": "by_id",
                    "position": position,
                    "scale": scale,
                },
            }

        params = {
            "action": "modify",
            "target": target,
            "searchMethod": "by_id",
            "position": position,
            "scale": scale,
        }
        if tag is not None:
            params["tag"] = tag
        return {"tool": "manage_gameobject", "params": params}

    @staticmethod
    def _has_component(item: dict[str, Any], component_name: str) -> bool:
        components = item.get("componentTypes") or item.get("componentNames") or []
        return component_name in components

    @staticmethod
    def _add_component_command(instance_id: int, component_type: str) -> dict[str, Any]:
        return {
            "tool": "manage_components",
            "params": {
                "action": "add",
                "target": instance_id,
                "search_method": "by_id",
                "component_type": component_type,
            },
        }
