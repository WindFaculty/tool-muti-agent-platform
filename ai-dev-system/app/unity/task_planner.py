from __future__ import annotations

import re

from app.agent.task_spec import TaskActionSpec


class UnityTaskPlanner:
    """Parse narrow natural-language prompts into structured Unity capabilities."""

    _ALIASES: dict[str, list[TaskActionSpec]] = {
        "attach editor": [TaskActionSpec(capability="editor.attach", backend="gui", allow_fallback=False)],
        "assert layout ready": [TaskActionSpec(capability="editor.layout.assert", backend="gui", allow_fallback=False)],
        "normalize layout": [TaskActionSpec(capability="editor.layout.normalize", backend="mcp", allow_fallback=False)],
        "dump control tree": [TaskActionSpec(capability="editor.control_tree.dump", backend="gui", allow_fallback=False)],
        "snapshot console": [TaskActionSpec(capability="editor.console.snapshot", backend="gui", allow_fallback=False)],
        "play": [TaskActionSpec(capability="editor.play")],
        "stop": [TaskActionSpec(capability="editor.stop")],
        "pause": [TaskActionSpec(capability="editor.pause")],
    }

    _FOCUS_PATTERN = re.compile(r"focus\s+(?P<surface>hierarchy|project|inspector|scene|game|console)$", re.IGNORECASE)
    _OPEN_WINDOW_PATTERN = re.compile(
        r"open\s+(?P<window>console|package manager|animator|ui builder)$",
        re.IGNORECASE,
    )
    _OPEN_SCENE_PATTERN = re.compile(
        r"(?:open|load)\s+scene\s+(?P<path>Assets/[A-Za-z0-9_./ -]+\.unity)$",
        re.IGNORECASE,
    )
    _CREATE_OBJECT_PATTERN = re.compile(
        r"create\s+(?P<kind>empty|cube|sphere|capsule|plane|quad)(?:\s+named\s+(?P<name>[A-Za-z0-9_ -]+))?$",
        re.IGNORECASE,
    )
    _DELETE_OBJECT_PATTERN = re.compile(r"delete\s+object\s+(?P<target>[A-Za-z0-9_ ./-]+)$", re.IGNORECASE)
    _ADD_COMPONENT_PATTERN = re.compile(
        r"add\s+component\s+(?P<component>[A-Za-z0-9_./ -]+)\s+to\s+(?P<target>[A-Za-z0-9_ ./-]+)$",
        re.IGNORECASE,
    )
    _SCREENSHOT_PATTERN = re.compile(
        r"capture\s+(?P<surface>scene|game)(?:\s+view)?$",
        re.IGNORECASE,
    )

    def build_actions(self, task: str) -> list[TaskActionSpec]:
        normalized = " ".join(task.strip().split()).lower()
        alias = self._ALIASES.get(normalized)
        if alias is not None:
            return [TaskActionSpec(**item.to_dict()) for item in alias]

        match = self._FOCUS_PATTERN.match(normalized)
        if match:
            return [TaskActionSpec(capability="editor.surface.focus", params={"surface": match.group("surface")})]

        match = self._OPEN_WINDOW_PATTERN.match(normalized)
        if match:
            return [TaskActionSpec(capability="editor.window.open", params={"window": match.group("window").title()})]

        match = self._OPEN_SCENE_PATTERN.match(task.strip())
        if match:
            return [TaskActionSpec(capability="scene.manage", params={"action": "load", "path": match.group("path")})]

        match = self._CREATE_OBJECT_PATTERN.match(normalized)
        if match:
            params = {
                "action": "create",
                "primitive_type": match.group("kind"),
                "name": match.group("name") or match.group("kind").title(),
            }
            return [TaskActionSpec(capability="gameobject.manage", params=params)]

        match = self._DELETE_OBJECT_PATTERN.match(normalized)
        if match:
            return [
                TaskActionSpec(
                    capability="gameobject.manage",
                    params={"action": "delete", "target": match.group("target"), "search_method": "by_name"},
                )
            ]

        match = self._ADD_COMPONENT_PATTERN.match(normalized)
        if match:
            return [
                TaskActionSpec(
                    capability="component.manage",
                    params={
                        "action": "add",
                        "target": match.group("target"),
                        "search_method": "by_name",
                        "component_type": match.group("component"),
                    },
                )
            ]

        match = self._SCREENSHOT_PATTERN.match(normalized)
        if match:
            return [
                TaskActionSpec(
                    capability="camera.manage",
                    params={"action": "screenshot", "camera": "Main Camera", "capture_source": "game_view"},
                )
            ]

        raise ValueError(
            "Unsupported Unity task. Use a structured actions[] task spec, or a narrow task such as "
            "'attach editor', 'assert layout ready', 'open scene Assets/Scenes/X.unity', "
            "'create cube named Player', 'add component Rigidbody to Player', or 'open package manager'."
        )
