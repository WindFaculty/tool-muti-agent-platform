from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.agent.state import SelectorSpec


@dataclass(frozen=True, slots=True)
class UnitySurfaceSpec:
    key: str
    display_name: str
    selector: SelectorSpec
    focus_hotkey: str | None = None
    menu_path: str | None = None
    fallback_region: tuple[float, float, float, float] | None = None


class UnitySurfaceMap:
    _REPO_ROOT = Path(__file__).resolve().parents[3]
    _PROJECT_ROOT = _REPO_ROOT / "unity-client"
    _LAYOUT_PATH = _PROJECT_ROOT / "UserSettings" / "Layouts" / "default-6000.dwlt"
    _EDITOR_PATH = Path(r"D:\6000.3.11f1\Editor\Unity.exe")
    _EDITOR_SELECTOR = SelectorSpec(
        title_re=r"^unity-client\b.*Unity 6\.3 LTS \(6000\.3\.11f1\).*",
        class_name="UnityContainerWndClass",
        backend="uia",
    )

    _SURFACES: dict[str, UnitySurfaceSpec] = {
        "toolbar": UnitySurfaceSpec(
            key="toolbar",
            display_name="Toolbar",
            selector=SelectorSpec(title="UnityEditor.MainToolbarWindow", control_type="Pane", backend="uia"),
            fallback_region=(0.0, 0.0, 1.0, 0.04),
        ),
        "hierarchy": UnitySurfaceSpec(
            key="hierarchy",
            display_name="Hierarchy",
            selector=SelectorSpec(title="UnityEditor.SceneHierarchyWindow", control_type="Pane", backend="uia"),
            focus_hotkey="^4",
            fallback_region=(0.0, 0.02, 0.20, 0.78),
        ),
        "inspector": UnitySurfaceSpec(
            key="inspector",
            display_name="Inspector",
            selector=SelectorSpec(title="UnityEditor.InspectorWindow", control_type="Pane", backend="uia"),
            focus_hotkey="^3",
            fallback_region=(0.73, 0.02, 1.0, 0.93),
        ),
        "console": UnitySurfaceSpec(
            key="console",
            display_name="Console",
            selector=SelectorSpec(title="UnityEditor.ConsoleWindow", control_type="Pane", backend="uia"),
            menu_path="Window->General->Console",
            fallback_region=(0.0, 0.78, 0.73, 0.93),
        ),
        "project": UnitySurfaceSpec(
            key="project",
            display_name="Project",
            selector=SelectorSpec(title="Project", control_type="Pane", backend="uia"),
            focus_hotkey="^5",
            fallback_region=(0.0, 0.56, 0.76, 0.93),
        ),
        "scene": UnitySurfaceSpec(
            key="scene",
            display_name="Scene",
            selector=SelectorSpec(title="UnityEditor.SceneView", control_type="Pane", backend="uia"),
            focus_hotkey="^1",
            fallback_region=(0.20, 0.08, 0.73, 0.77),
        ),
        "game": UnitySurfaceSpec(
            key="game",
            display_name="Game",
            selector=SelectorSpec(title="UnityEditor.GameView", control_type="Pane", backend="uia"),
            focus_hotkey="^2",
            fallback_region=(0.20, 0.08, 0.73, 0.77),
        ),
        "animator": UnitySurfaceSpec(
            key="animator",
            display_name="Animator",
            selector=SelectorSpec(title_re=r".*Animator.*", control_type="Pane", backend="uia"),
            menu_path="Window->Animation->Animator",
            fallback_region=(0.20, 0.08, 0.73, 0.77),
        ),
        "package-manager": UnitySurfaceSpec(
            key="package-manager",
            display_name="Package Manager",
            selector=SelectorSpec(title_re=r".*Package Manager.*", control_type="Pane", backend="uia"),
            menu_path="Window->Package Management->Package Manager",
            fallback_region=(0.20, 0.08, 0.73, 0.77),
        ),
        "ui-builder": UnitySurfaceSpec(
            key="ui-builder",
            display_name="UI Builder",
            selector=SelectorSpec(title_re=r".*UI Builder.*", control_type="Pane", backend="uia"),
            menu_path="Window->UI Toolkit->UI Builder",
            fallback_region=(0.20, 0.08, 0.73, 0.77),
        ),
    }

    _WINDOW_ALIASES = {
        "Console": "console",
        "Package Manager": "package-manager",
        "Animator": "animator",
        "UI Builder": "ui-builder",
        "Project": "project",
        "Inspector": "inspector",
        "Hierarchy": "hierarchy",
        "Scene": "scene",
        "Game": "game",
    }

    _DEFAULT_LAYOUT_KEYS = ("toolbar", "hierarchy", "inspector", "console", "game")

    @classmethod
    def project_root(cls) -> Path:
        return cls._PROJECT_ROOT

    @classmethod
    def layout_path(cls) -> Path:
        return cls._LAYOUT_PATH

    @classmethod
    def editor_path(cls) -> Path:
        return cls._EDITOR_PATH

    @classmethod
    def editor_selector(cls) -> SelectorSpec:
        return cls._EDITOR_SELECTOR

    @classmethod
    def surface(cls, key: str) -> UnitySurfaceSpec:
        normalized = key.strip().lower()
        if normalized not in cls._SURFACES:
            known = ", ".join(sorted(cls._SURFACES))
            raise ValueError(f"Unknown Unity surface '{key}'. Known surfaces: {known}")
        return cls._SURFACES[normalized]

    @classmethod
    def all_surfaces(cls) -> dict[str, UnitySurfaceSpec]:
        return dict(cls._SURFACES)

    @classmethod
    def resolve_window_alias(cls, name: str) -> UnitySurfaceSpec:
        key = cls._WINDOW_ALIASES.get(name)
        if key is None:
            known = ", ".join(cls._WINDOW_ALIASES)
            raise ValueError(f"Unsupported Unity window '{name}'. Supported windows: {known}")
        return cls.surface(key)

    @classmethod
    def layout_surface_names(cls, requires_layout: str | None) -> list[str]:
        if requires_layout and requires_layout != "default-6000":
            raise ValueError(f"Unsupported Unity layout '{requires_layout}'. Only 'default-6000' is supported.")
        return list(cls._DEFAULT_LAYOUT_KEYS)
