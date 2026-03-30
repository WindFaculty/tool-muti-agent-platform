from __future__ import annotations

import time


class MpcToolStrategy:
    """Execute a single Unity MCP tool call inside the GUI-agent flow."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "mcp_tool"

    def execute(self, ctx) -> None:
        run_context = ctx.metadata.get("run_context") or {}
        runtime = run_context.get("unity_runtime")
        if runtime is None:
            raise RuntimeError("Unity MCP runtime is not available for this action.")
        job_tracker = run_context.get("job_tracker")

        tool_name = str(ctx.action.metadata.get("tool_name") or ctx.action.value or "")
        if not tool_name:
            raise RuntimeError("MCP action is missing a tool name.")

        params = dict(ctx.action.metadata.get("tool_params") or {})
        execution = dict(ctx.action.metadata.get("execution") or {})
        execution_mode = str(execution.get("mode") or "blocking")
        job_key = str(execution.get("job_key") or ctx.action.metadata.get("job_key") or ctx.action.name)
        if execution_mode == "background_job_wait":
            if job_tracker is None:
                raise RuntimeError("Background job wait requested but no JobTracker is available.")
            job = job_tracker.get(job_key)
            params.setdefault("job_id", job.job_id)
            if "wait_timeout" not in params and "wait_timeout" in execution:
                params["wait_timeout"] = execution["wait_timeout"]
        result = runtime.call_tool(tool_name, params)
        if execution_mode == "blocking":
            result = self._resolve_pending(runtime, tool_name, params, result)
        elif execution_mode == "background_job_start":
            if job_tracker is None:
                raise RuntimeError("Background job start requested but no JobTracker is available.")
            structured = result.get("structured_content") or {}
            data = structured.get("data") or {}
            job_id = data.get("job_id")
            if not job_id:
                raise RuntimeError(f"MCP tool '{tool_name}' did not return a job_id for background execution.")
            status_tool = _status_tool_name(tool_name)
            job_tracker.start(job_key=job_key, tool_name=tool_name, status_tool=status_tool, job_id=str(job_id), params=params)
            ctx.metadata["background_job"] = {
                "job_key": job_key,
                "job_id": str(job_id),
                "status_tool": status_tool,
                "status": "started",
            }
        elif execution_mode == "background_job_wait":
            if job_tracker is None:
                raise RuntimeError("Background job wait requested but no JobTracker is available.")
            status = _resolve_job_status(result)
            job_tracker.update(job_key, status=status, result=result)
            ctx.metadata["background_job"] = {
                "job_key": job_key,
                "job_id": params.get("job_id"),
                "status_tool": tool_name,
                "status": status,
            }
        ctx.metadata["mcp_tool_name"] = tool_name
        ctx.metadata["mcp_tool_params"] = params
        ctx.metadata["mcp_result"] = result

    @staticmethod
    def _resolve_pending(runtime, tool_name: str, params: dict, result: dict) -> dict:
        structured = result.get("structured_content") or {}
        if structured.get("_mcp_status") != "pending":
            return result

        data = structured.get("data") or {}
        job_id = data.get("job_id")
        if not job_id:
            return result

        if tool_name == "run_tests":
            return runtime.call_tool("get_test_job", {"job_id": job_id, "wait_timeout": params.get("wait_timeout", 30)})

        if tool_name == "manage_packages":
            return runtime.call_tool("manage_packages", {"action": "status", "job_id": job_id})

        if tool_name == "manage_build" and params.get("wait_for_completion"):
            deadline = time.time() + float(params.get("wait_timeout", 120))
            latest = result
            while time.time() < deadline:
                latest = runtime.call_tool("manage_build", {"action": "status", "job_id": job_id})
                latest_structured = latest.get("structured_content") or {}
                latest_data = latest_structured.get("data") or {}
                status = str(latest_data.get("status") or latest_structured.get("status") or "").lower()
                if status in {"succeeded", "failed", "cancelled", "completed"}:
                    return latest
                time.sleep(1.0)
            return latest

        return result


class MpcBatchStrategy:
    """Execute a Unity MCP batch command payload."""

    def can_handle(self, strategy_name: str) -> bool:
        return strategy_name == "mcp_batch"

    def execute(self, ctx) -> None:
        run_context = ctx.metadata.get("run_context") or {}
        runtime = run_context.get("unity_runtime")
        if runtime is None:
            raise RuntimeError("Unity MCP runtime is not available for this action.")

        commands = list(ctx.action.metadata.get("tool_params", {}).get("commands") or [])
        if not commands:
            raise RuntimeError("MCP batch action is missing commands[].")

        result = runtime.call_tool(
            "batch_execute",
            {
                "commands": commands,
                "fail_fast": ctx.action.metadata.get("tool_params", {}).get("fail_fast", True),
                "parallel": ctx.action.metadata.get("tool_params", {}).get("parallel", False),
            },
        )
        ctx.metadata["mcp_batch_result"] = result


def _status_tool_name(tool_name: str) -> str:
    if tool_name == "run_tests":
        return "get_test_job"
    if tool_name == "manage_packages":
        return "manage_packages"
    if tool_name == "manage_build":
        return "manage_build"
    return tool_name


def _resolve_job_status(result: dict) -> str:
    structured = result.get("structured_content") or {}
    data = structured.get("data") or {}
    status = str(data.get("status") or structured.get("status") or "").strip().lower()
    if status in {"succeeded", "completed", "success"}:
        return "completed"
    if status in {"failed", "cancelled", "canceled"}:
        return "failed"
    return status or "pending"
