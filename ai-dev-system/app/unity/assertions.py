from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.task_spec import TaskVerifySpec
from app.unity.surfaces import UnitySurfaceMap


class UnityAssertionRunner:
    def run(self, verify_specs: list[TaskVerifySpec], *, runtime) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        passed = True
        for spec in verify_specs:
            result = self._run_single(spec, runtime=runtime)
            checks.append(result)
            if not result.get("passed", False):
                passed = False
        return {"passed": passed, "checks": checks}

    def _run_single(self, spec: TaskVerifySpec, *, runtime) -> dict[str, Any]:
        kind = spec.kind
        params = spec.params

        if kind == "active_scene_path_is":
            result = runtime.call_tool("manage_scene", {"action": "get_active"})
            actual = ((result.get("structured_content") or {}).get("data") or {}).get("path")
            expected = params.get("path")
            return {"kind": kind, "passed": actual == expected, "expected": expected, "actual": actual}

        if kind == "gameobject_exists":
            result = runtime.call_tool(
                "find_gameobjects",
                {"search_term": params["name"], "search_method": params.get("search_method", "by_name")},
            )
            data = (result.get("structured_content") or {}).get("data") or {}
            count = int(data.get("totalCount") or 0)
            return {"kind": kind, "passed": count > 0, "expected": params["name"], "actual_count": count}

        if kind == "component_exists":
            target_name = str(params["target"])
            search = runtime.call_tool("find_gameobjects", {"search_term": target_name, "search_method": "by_name"})
            ids = (((search.get("structured_content") or {}).get("data") or {}).get("instanceIDs") or [])
            if not ids:
                return {"kind": kind, "passed": False, "error": f"GameObject '{target_name}' was not found."}
            payload = runtime.read_json_resource(f"mcpforunity://scene/gameobject/{ids[0]}/components")
            components = ((payload.get("data") or {}).get("components") or [])
            actual_types = [str(component.get("typeName") or "") for component in components]
            component_name = str(params["component"])
            passed = any(item == component_name or item.endswith(f".{component_name}") for item in actual_types)
            return {
                "kind": kind,
                "passed": passed,
                "target": target_name,
                "expected_component": component_name,
                "actual_components": actual_types,
            }

        if kind == "asset_exists":
            relative_path = str(params["path"]).replace("\\", "/")
            asset_path = UnitySurfaceMap.project_root() / relative_path.replace("Assets/", "", 1)
            if relative_path.startswith("Assets/"):
                asset_path = UnitySurfaceMap.project_root() / relative_path
            passed = asset_path.exists()
            return {"kind": kind, "passed": passed, "path": relative_path, "resolved_path": str(asset_path)}

        if kind == "package_installed":
            result = runtime.call_tool("manage_packages", {"action": "list_packages"})
            structured = result.get("structured_content") or {}
            if structured.get("_mcp_status") == "pending":
                job_id = ((structured.get("data") or {}).get("job_id"))
                if job_id:
                    result = runtime.call_tool("manage_packages", {"action": "status", "job_id": job_id})
                    structured = result.get("structured_content") or {}
            entries = ((structured.get("data") or {}).get("packages") or [])
            package_name = str(params["package"])
            installed = any(str(item.get("name") or "") == package_name for item in entries if isinstance(item, dict))
            return {"kind": kind, "passed": installed, "package": package_name, "package_count": len(entries)}

        if kind == "tool_group_active":
            result = runtime.call_tool("manage_tools", {"action": "list_groups"})
            groups = (result.get("structured_content") or {}).get("groups") or []
            name = str(params["group"])
            match = next((group for group in groups if group.get("name") == name), None)
            enabled = bool(match and match.get("enabled"))
            return {"kind": kind, "passed": enabled, "group": name, "actual": match}

        if kind == "build_succeeded":
            result = runtime.call_tool("manage_build", {"action": "status", "job_id": params["job_id"]})
            structured = result.get("structured_content") or {}
            data = structured.get("data") or {}
            passed = str(data.get("status") or "").lower() == "succeeded"
            return {"kind": kind, "passed": passed, "actual": data}

        if kind == "test_job_passed":
            result = runtime.call_tool("get_test_job", {"job_id": params["job_id"], "wait_timeout": params.get("wait_timeout", 10)})
            structured = result.get("structured_content") or {}
            data = structured.get("data") or {}
            passed = str(data.get("status") or "").lower() == "completed" and int(data.get("failedCount") or 0) == 0
            return {"kind": kind, "passed": passed, "actual": data}

        raise ValueError(f"Unsupported Unity verification kind: {kind}")
