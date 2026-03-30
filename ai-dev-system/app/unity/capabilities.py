from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent.state import ActionRequest, VerificationCheck
from app.agent.task_spec import TaskActionSpec, TaskSpec
from app.unity.macros import UnityMacroRegistry


_CAPABILITY_STATUSES = {
    "supported_via_mcp",
    "supported_via_gui_fallback",
    "manual_validation_required",
    "unsupported",
}


@dataclass(frozen=True, slots=True)
class UnityCapabilitySpec:
    capability: str
    category: str
    description: str
    preferred_backend: str
    tool_name: str | None = None
    default_params: dict[str, Any] = field(default_factory=dict)
    gui_macro: str | None = None
    gui_fallback_macro: str | None = None
    fallbackable: bool = False
    manual_validation_required: bool = False

    def resolved_status(self, *, tools: set[str]) -> str:
        has_mcp = bool(self.tool_name and self.tool_name in tools)
        has_gui = bool(self.gui_macro or self.gui_fallback_macro)
        if self.preferred_backend == "mcp":
            if has_mcp:
                return "manual_validation_required" if self.manual_validation_required else "supported_via_mcp"
            if self.fallbackable and has_gui:
                return "supported_via_gui_fallback"
            return "unsupported"
        if has_gui:
            return "manual_validation_required" if self.manual_validation_required else "supported_via_gui_fallback"
        if has_mcp:
            return "manual_validation_required" if self.manual_validation_required else "supported_via_mcp"
        return "unsupported"

    def to_matrix_row(self, *, tools: set[str], resources: set[str]) -> dict[str, Any]:
        status = self.resolved_status(tools=tools)
        assert status in _CAPABILITY_STATUSES
        resolved_backend = None
        if status == "supported_via_mcp":
            resolved_backend = "mcp"
        elif status == "supported_via_gui_fallback":
            resolved_backend = "gui"
        elif status == "manual_validation_required":
            resolved_backend = "mcp" if self.tool_name and self.tool_name in tools else "gui"
        return {
            "capability": self.capability,
            "category": self.category,
            "description": self.description,
            "status": status,
            "resolved_backend": resolved_backend,
            "preferred_backend": self.preferred_backend,
            "tool_name": self.tool_name,
            "gui_macro": self.gui_macro or self.gui_fallback_macro,
            "manual_validation_required": self.manual_validation_required,
            "tool_available": bool(self.tool_name and self.tool_name in tools),
            "resources_visible": sorted(resources),
        }


class UnityCapabilityRegistry:
    @classmethod
    def names(cls) -> list[str]:
        return sorted(cls._SPECS)

    @classmethod
    def get(cls, capability: str) -> UnityCapabilitySpec:
        if capability not in cls._SPECS:
            known = ", ".join(sorted(cls._SPECS))
            raise ValueError(f"Unknown Unity capability '{capability}'. Known capabilities: {known}")
        return cls._SPECS[capability]

    @classmethod
    def build_matrix(cls, *, tools: list[str], resources: list[str]) -> list[dict[str, Any]]:
        tool_set = set(tools)
        resource_set = set(resources)
        return [cls.get(name).to_matrix_row(tools=tool_set, resources=resource_set) for name in cls.names()]

    @classmethod
    def compile_actions(
        cls,
        *,
        task_spec: TaskSpec,
        tools: list[str],
        resources: list[str],
    ) -> list[ActionRequest]:
        compiled: list[ActionRequest] = []
        tool_set = set(tools)
        resource_set = set(resources)
        for index, action in enumerate(task_spec.actions):
            compiled.extend(cls._compile_action(task_spec, action, index=index, tools=tool_set, resources=resource_set))
        return compiled

    @classmethod
    def _compile_action(
        cls,
        task_spec: TaskSpec,
        action: TaskActionSpec,
        *,
        index: int,
        tools: set[str],
        resources: set[str],
    ) -> list[ActionRequest]:
        del resources
        spec = cls.get(action.capability)
        requested_backend = action.backend
        if requested_backend not in {"auto", "mcp", "gui"}:
            raise ValueError(f"Unsupported backend '{requested_backend}' for capability '{action.capability}'.")

        if action.capability == "editor.layout.normalize":
            if requested_backend == "gui":
                raise ValueError("editor.layout.normalize is only supported through MCP-backed execution.")
            return [cls._compile_layout_normalize_action(action=action, index=index, task_spec=task_spec, tools=tools)]

        if requested_backend == "gui":
            return cls._compile_gui_action(spec, action, index=index, task_spec=task_spec)

        has_mcp = bool(spec.tool_name and spec.tool_name in tools)
        if requested_backend == "mcp":
            if not has_mcp:
                raise ValueError(f"Capability '{action.capability}' requested MCP backend, but tool '{spec.tool_name}' is unavailable.")
            return [cls._compile_mcp_action(spec, action, index=index)]

        if has_mcp and spec.preferred_backend == "mcp":
            return [cls._compile_mcp_action(spec, action, index=index)]

        if spec.preferred_backend == "gui":
            return cls._compile_gui_action(spec, action, index=index, task_spec=task_spec)

        if action.allow_fallback and spec.fallbackable:
            return cls._compile_gui_action(spec, action, index=index, task_spec=task_spec)

        if has_mcp:
            return [cls._compile_mcp_action(spec, action, index=index)]

        raise ValueError(
            f"Capability '{action.capability}' is unsupported on this machine/project. "
            f"Preferred backend='{spec.preferred_backend}', tool='{spec.tool_name}'."
        )

    @classmethod
    def _compile_layout_normalize_action(
        cls,
        *,
        action: TaskActionSpec,
        index: int,
        task_spec: TaskSpec,
        tools: set[str],
    ) -> ActionRequest:
        if "batch_execute" not in tools:
            raise ValueError("Capability 'editor.layout.normalize' requires the Unity MCP tool 'batch_execute'.")
        layout_name = str(
            action.params.get("layout")
            or task_spec.layout_policy.get("required")
            or task_spec.requires_layout
            or "default-6000"
        )
        commands = [
            {"tool": "execute_menu_item", "params": {"menu_path": f"Window/Layouts/{layout_name}"}},
            {"tool": "execute_menu_item", "params": {"menu_path": f"Window/Layout/{layout_name}"}},
            {"tool": "execute_menu_item", "params": {"menu_path": f"Window/Layouts/Load Layout/{layout_name}"}},
            {"tool": "execute_menu_item", "params": {"menu_path": f"Window/Layout/Load Layout/{layout_name}"}},
        ]
        return ActionRequest(
            name=f"{index:02d}_editor_layout_normalize",
            action_type="mcp_batch",
            value="batch_execute",
            allowed_strategies=["mcp_batch"],
            destructive=False,
            metadata={
                "capability": "editor.layout.normalize",
                "tool_name": "batch_execute",
                "tool_params": {
                    "commands": commands,
                    "fail_fast": False,
                    "parallel": False,
                },
                "resolved_backend": "mcp",
                "requested_backend": action.backend,
                "heal_hints": dict(action.heal_hints),
                "execution": dict(action.execution),
            },
            postconditions=[VerificationCheck(kind="mcp_batch_success")],
        )

    @classmethod
    def _compile_mcp_action(cls, spec: UnityCapabilitySpec, action: TaskActionSpec, *, index: int) -> ActionRequest:
        assert spec.tool_name is not None
        params = dict(spec.default_params)
        params.update(action.params)
        action_type = "mcp_batch" if spec.tool_name == "batch_execute" else "mcp_tool"
        execution = dict(action.execution)
        verify_kind = "mcp_batch_success" if action_type == "mcp_batch" else "mcp_result_success"
        if action_type == "mcp_tool":
            execution_mode = str(execution.get("mode") or "blocking")
            if execution_mode == "background_job_start":
                verify_kind = "mcp_job_started"
            elif execution_mode == "background_job_wait":
                verify_kind = "mcp_job_completed"
        return ActionRequest(
            name=f"{index:02d}_{spec.capability.replace('.', '_')}",
            action_type=action_type,
            value=spec.tool_name,
            allowed_strategies=[action_type],
            destructive=bool(params.get("action") in {"build", "delete", "remove", "modify", "create"}),
            metadata={
                "capability": spec.capability,
                "tool_name": spec.tool_name,
                "tool_params": params,
                "resolved_backend": "mcp",
                "requested_backend": action.backend,
                "heal_hints": dict(action.heal_hints),
                "execution": execution,
            },
            postconditions=[VerificationCheck(kind=verify_kind)],
        )

    @classmethod
    def _compile_gui_action(
        cls,
        spec: UnityCapabilitySpec,
        action: TaskActionSpec,
        *,
        index: int,
        task_spec: TaskSpec,
    ) -> list[ActionRequest]:
        macro = cls._resolve_gui_macro(spec, action)
        legacy = TaskSpec(
            profile=task_spec.profile,
            macro=macro["name"],
            args=macro["args"],
            confirm_destructive=task_spec.confirm_destructive,
            dry_run=task_spec.dry_run,
            requires_layout=task_spec.requires_layout or "default-6000",
            evidence=dict(task_spec.evidence),
            metadata=dict(task_spec.metadata),
        )
        compiled = UnityMacroRegistry.build_plan(legacy)
        for item in compiled:
            item.metadata.setdefault("capability", spec.capability)
            item.metadata.setdefault("resolved_backend", "gui")
            item.metadata.setdefault("requested_backend", action.backend)
            item.metadata.setdefault("heal_hints", dict(action.heal_hints))
            item.metadata.setdefault("execution", dict(action.execution))
            item.name = f"{index:02d}_{item.name}"
        return compiled

    @staticmethod
    def _resolve_gui_macro(spec: UnityCapabilitySpec, action: TaskActionSpec) -> dict[str, Any]:
        if spec.capability == "editor.surface.focus":
            surface = str(action.params.get("surface") or "").strip().lower().replace("-", "_").replace(" ", "_")
            mapping = {
                "hierarchy": "focus_hierarchy",
                "project": "focus_project",
                "inspector": "focus_inspector",
                "scene": "focus_scene_view",
                "game": "focus_game_view",
                "console": "focus_console",
            }
            if surface not in mapping:
                raise ValueError("editor.surface.focus requires params.surface in {hierarchy, project, inspector, scene, game, console}.")
            return {"name": mapping[surface], "args": {}}

        if spec.capability == "editor.window.open":
            window = str(action.params.get("window") or "").strip()
            if not window:
                raise ValueError("editor.window.open requires params.window.")
            return {"name": "open_window", "args": {"window": window}}

        if spec.capability == "editor.view.capture":
            surface = str(action.params.get("surface") or "game").strip().lower()
            return {"name": "capture_view", "args": {"surface": surface}}

        macro = spec.gui_macro or spec.gui_fallback_macro
        if not macro:
            raise ValueError(f"Capability '{spec.capability}' does not define a GUI macro.")
        return {"name": macro, "args": dict(action.params)}

    _SPECS: dict[str, UnityCapabilitySpec] = {
        "animation.manage": UnityCapabilitySpec(
            capability="animation.manage",
            category="animation",
            description="Run supported animation and animator-controller operations exposed by manage_animation.",
            preferred_backend="mcp",
            tool_name="manage_animation",
        ),
        "animator.graph.manage": UnityCapabilitySpec(
            capability="animator.graph.manage",
            category="animation",
            description="Manage Animator controller graphs through manage_animation controller_* operations.",
            preferred_backend="mcp",
            tool_name="manage_animation",
            manual_validation_required=True,
        ),
        "asset.manage": UnityCapabilitySpec(
            capability="asset.manage",
            category="asset",
            description="Run any supported manage_asset operation.",
            preferred_backend="mcp",
            tool_name="manage_asset",
        ),
        "build.manage": UnityCapabilitySpec(
            capability="build.manage",
            category="build",
            description="Run any supported manage_build operation.",
            preferred_backend="mcp",
            tool_name="manage_build",
            manual_validation_required=True,
        ),
        "camera.manage": UnityCapabilitySpec(
            capability="camera.manage",
            category="camera",
            description="Run any supported manage_camera operation.",
            preferred_backend="mcp",
            tool_name="manage_camera",
        ),
        "component.manage": UnityCapabilitySpec(
            capability="component.manage",
            category="component",
            description="Run any supported manage_components operation.",
            preferred_backend="mcp",
            tool_name="manage_components",
        ),
        "editor.attach": UnityCapabilitySpec(
            capability="editor.attach",
            category="editor",
            description="Attach to or launch the current Unity editor window.",
            preferred_backend="gui",
            gui_macro="attach_editor",
        ),
        "editor.console.snapshot": UnityCapabilitySpec(
            capability="editor.console.snapshot",
            category="editor",
            description="Copy and persist the visible Unity console text.",
            preferred_backend="gui",
            gui_macro="snapshot_console",
            manual_validation_required=True,
        ),
        "editor.control_tree.dump": UnityCapabilitySpec(
            capability="editor.control_tree.dump",
            category="editor",
            description="Dump UI Automation control trees for the active Unity editor window.",
            preferred_backend="gui",
            gui_macro="dump_control_tree",
        ),
        "editor.layout.assert": UnityCapabilitySpec(
            capability="editor.layout.assert",
            category="editor",
            description="Assert the pinned Unity layout and modal state before automation.",
            preferred_backend="gui",
            gui_macro="assert_layout_ready",
        ),
        "editor.layout.normalize": UnityCapabilitySpec(
            capability="editor.layout.normalize",
            category="editor",
            description="Normalize the Unity editor layout through MCP-backed menu execution before GUI fallback work.",
            preferred_backend="mcp",
            tool_name="batch_execute",
            manual_validation_required=True,
        ),
        "editor.manage": UnityCapabilitySpec(
            capability="editor.manage",
            category="editor",
            description="Run any supported manage_editor operation.",
            preferred_backend="mcp",
            tool_name="manage_editor",
            fallbackable=True,
        ),
        "editor.pause": UnityCapabilitySpec(
            capability="editor.pause",
            category="editor",
            description="Pause play mode.",
            preferred_backend="mcp",
            tool_name="manage_editor",
            default_params={"action": "pause"},
            gui_fallback_macro="pause_mode",
            fallbackable=True,
        ),
        "editor.play": UnityCapabilitySpec(
            capability="editor.play",
            category="editor",
            description="Enter play mode.",
            preferred_backend="mcp",
            tool_name="manage_editor",
            default_params={"action": "play"},
            gui_fallback_macro="play_mode",
            fallbackable=True,
        ),
        "editor.stop": UnityCapabilitySpec(
            capability="editor.stop",
            category="editor",
            description="Stop play mode.",
            preferred_backend="mcp",
            tool_name="manage_editor",
            default_params={"action": "stop"},
            gui_fallback_macro="stop_mode",
            fallbackable=True,
        ),
        "editor.surface.focus": UnityCapabilitySpec(
            capability="editor.surface.focus",
            category="editor",
            description="Focus a pinned Unity surface in the current layout.",
            preferred_backend="gui",
            gui_macro="focus_hierarchy",
        ),
        "editor.view.capture": UnityCapabilitySpec(
            capability="editor.view.capture",
            category="editor",
            description="Capture a pinned Unity surface by GUI coordinates.",
            preferred_backend="gui",
            gui_macro="capture_view",
            manual_validation_required=True,
        ),
        "editor.window.open": UnityCapabilitySpec(
            capability="editor.window.open",
            category="editor",
            description="Open a Unity editor window through the Window menu.",
            preferred_backend="gui",
            gui_macro="open_window",
            manual_validation_required=True,
        ),
        "gameobject.manage": UnityCapabilitySpec(
            capability="gameobject.manage",
            category="gameobject",
            description="Run any supported manage_gameobject operation.",
            preferred_backend="mcp",
            tool_name="manage_gameobject",
        ),
        "graphics.manage": UnityCapabilitySpec(
            capability="graphics.manage",
            category="graphics",
            description="Run any supported manage_graphics operation.",
            preferred_backend="mcp",
            tool_name="manage_graphics",
            manual_validation_required=True,
        ),
        "material.manage": UnityCapabilitySpec(
            capability="material.manage",
            category="material",
            description="Run any supported manage_material operation.",
            preferred_backend="mcp",
            tool_name="manage_material",
        ),
        "package.manage": UnityCapabilitySpec(
            capability="package.manage",
            category="package",
            description="Run any supported manage_packages operation.",
            preferred_backend="mcp",
            tool_name="manage_packages",
            manual_validation_required=True,
        ),
        "prefab.manage": UnityCapabilitySpec(
            capability="prefab.manage",
            category="prefab",
            description="Run any supported manage_prefabs operation.",
            preferred_backend="mcp",
            tool_name="manage_prefabs",
        ),
        "scene.manage": UnityCapabilitySpec(
            capability="scene.manage",
            category="scene",
            description="Run any supported manage_scene operation.",
            preferred_backend="mcp",
            tool_name="manage_scene",
        ),
        "shader.graph.manage": UnityCapabilitySpec(
            capability="shader.graph.manage",
            category="graphics",
            description="Planned Shader Graph node-graph mutations. Backend graph operations are not yet available.",
            preferred_backend="mcp",
        ),
        "shader.manage": UnityCapabilitySpec(
            capability="shader.manage",
            category="graphics",
            description="Run supported manage_shader operations for shader script assets.",
            preferred_backend="mcp",
            tool_name="manage_shader",
            manual_validation_required=True,
        ),
        "texture.manage": UnityCapabilitySpec(
            capability="texture.manage",
            category="graphics",
            description="Run supported manage_texture operations for generated or procedural textures.",
            preferred_backend="mcp",
            tool_name="manage_texture",
            manual_validation_required=True,
        ),
        "timeline.manage": UnityCapabilitySpec(
            capability="timeline.manage",
            category="animation",
            description="Planned Timeline graph mutations. Backend timeline graph operations are not yet available.",
            preferred_backend="mcp",
        ),
        "tests.run": UnityCapabilitySpec(
            capability="tests.run",
            category="tests",
            description="Start a Unity test run.",
            preferred_backend="mcp",
            tool_name="run_tests",
            manual_validation_required=True,
        ),
        "tests.status": UnityCapabilitySpec(
            capability="tests.status",
            category="tests",
            description="Poll a running Unity test job.",
            preferred_backend="mcp",
            tool_name="get_test_job",
            manual_validation_required=True,
        ),
        "ui.manage": UnityCapabilitySpec(
            capability="ui.manage",
            category="ui",
            description="Run any supported manage_ui operation.",
            preferred_backend="mcp",
            tool_name="manage_ui",
            manual_validation_required=True,
        ),
        "vfx.graph.manage": UnityCapabilitySpec(
            capability="vfx.graph.manage",
            category="graphics",
            description="Planned VFX Graph node-graph mutations. Backend graph operations are not yet available.",
            preferred_backend="mcp",
        ),
        "vfx.manage": UnityCapabilitySpec(
            capability="vfx.manage",
            category="graphics",
            description="Run supported manage_vfx operations for particle and visual-effect components.",
            preferred_backend="mcp",
            tool_name="manage_vfx",
            manual_validation_required=True,
        ),
    }
