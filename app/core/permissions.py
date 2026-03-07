from __future__ import annotations

import os
import shlex
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from app.core.errors import PermissionDeniedError

DEFAULT_DANGEROUS_TOKENS = [
    "rm -rf",
    "del /f /s /q",
    "format c:",
    "shutdown",
    "reboot",
    "invoke-expression",
    "set-executionpolicy",
    "powershell -enc",
    "net user",
    "chmod 777 /",
]

PATH_KEYS = {
    "path",
    "file_path",
    "cwd",
    "context_path",
    "dockerfile",
    "project_path",
    "target_path",
}


class PermissionEngine:
    def __init__(self, policy_path: Path, workspace_root: Path) -> None:
        self.policy_path = policy_path
        self.workspace_root = workspace_root.resolve()
        self._lock = threading.Lock()
        self._policy: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        with self._lock:
            if self.policy_path.exists():
                data = yaml.safe_load(self.policy_path.read_text(encoding="utf-8"))
                self._policy = data or {}
            else:
                self._policy = {}

    def get_agent_policy(self, agent_id: str) -> dict[str, Any]:
        agents = self._policy.get("agents", {})
        default_policy = agents.get("default", {})
        specific_policy = agents.get(agent_id, {})
        return self._merge_dict(default_policy, specific_policy)

    def policy_snapshot(self, agent_id: str) -> dict[str, Any]:
        return self.get_agent_policy(agent_id)

    def check_tool_access(self, agent_id: str, tool_name: str) -> None:
        policy = self.get_agent_policy(agent_id)
        allow_tools = policy.get("allow_tools", ["*"])
        deny_tools = policy.get("deny_tools", [])

        if tool_name in deny_tools:
            raise PermissionDeniedError(f"Tool '{tool_name}' is explicitly denied")

        if "*" not in allow_tools and tool_name not in allow_tools:
            raise PermissionDeniedError(f"Tool '{tool_name}' is not allowed for this agent")

    def enforce_input(self, agent_id: str, tool_name: str, input_data: dict[str, Any]) -> None:
        policy = self.get_agent_policy(agent_id)
        for key, value in (input_data or {}).items():
            self._enforce_value(policy, tool_name, key, value)

    def validate_command(self, agent_id: str, tool_name: str, command: Any) -> None:
        policy = self.get_agent_policy(agent_id)
        self._validate_command(policy, tool_name, command)

    def _enforce_value(
        self,
        policy: dict[str, Any],
        tool_name: str,
        key: str,
        value: Any,
    ) -> None:
        key_lower = key.lower()
        if value is None:
            return

        if (
            key_lower in PATH_KEYS
            or key_lower.endswith("_path")
            or key_lower.endswith("_dir")
        ) and isinstance(value, str):
            self._validate_path(policy, value)
            return

        if key_lower in {"paths", "files", "roots"} and isinstance(value, list):
            for path_value in value:
                if isinstance(path_value, str):
                    self._validate_path(policy, path_value)
            return

        if key_lower in {"command", "cmd"}:
            self._validate_command(policy, tool_name, value)
            return

        if key_lower in {"url"} and isinstance(value, str):
            self._validate_network(policy, value)
            return

        if key_lower in {"urls"} and isinstance(value, list):
            for url_value in value:
                if isinstance(url_value, str):
                    self._validate_network(policy, url_value)

    def _validate_path(self, policy: dict[str, Any], raw_path: str) -> None:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate
        candidate = candidate.resolve(strict=False)

        roots = policy.get("path_roots") or [str(self.workspace_root)]
        for raw_root in roots:
            root = Path(raw_root).expanduser()
            if not root.is_absolute():
                root = self.workspace_root / root
            root = root.resolve(strict=False)

            if self._is_path_under(candidate, root):
                return

        raise PermissionDeniedError(f"Path '{raw_path}' is outside allowed roots")

    def _validate_command(self, policy: dict[str, Any], tool_name: str, command: Any) -> None:
        allow_map: dict[str, list[str]] = policy.get("command_allowlist", {})
        allowed_prefixes = [
            prefix.lower()
            for prefix in allow_map.get(tool_name, []) + allow_map.get("*", [])
        ]
        command_prefix = self._command_prefix(command)

        if allowed_prefixes and command_prefix not in allowed_prefixes:
            raise PermissionDeniedError(
                f"Command prefix '{command_prefix}' is not allowed for tool '{tool_name}'"
            )

        command_text = self._command_text(command).lower()
        dangerous_tokens = self._policy.get("dangerous_tokens", DEFAULT_DANGEROUS_TOKENS)
        for token in dangerous_tokens:
            if token.lower() in command_text:
                raise PermissionDeniedError(f"Command contains dangerous token '{token}'")

    def _validate_network(self, policy: dict[str, Any], raw_url: str) -> None:
        allowlist = policy.get("network_allowlist", ["*"])
        if "*" in allowlist:
            return

        parsed = urlparse(raw_url)
        host = (parsed.hostname or "").lower()
        for raw_domain in allowlist:
            domain = raw_domain.lower()
            if host == domain or host.endswith(f".{domain}"):
                return

        raise PermissionDeniedError(f"Domain '{host}' is not allowed")

    @staticmethod
    def _is_path_under(candidate: Path, root: Path) -> bool:
        candidate_norm = os.path.normcase(str(candidate))
        root_norm = os.path.normcase(str(root))
        try:
            common = os.path.commonpath([candidate_norm, root_norm])
        except ValueError:
            return False
        return common == root_norm

    @staticmethod
    def _command_prefix(command: Any) -> str:
        if isinstance(command, list) and command:
            return Path(str(command[0])).name.lower()
        if isinstance(command, str):
            split = shlex.split(command, posix=False)
            if split:
                return Path(split[0]).name.lower()
        return ""

    @staticmethod
    def _command_text(command: Any) -> str:
        if isinstance(command, list):
            return " ".join(str(part) for part in command)
        return str(command or "")

    @staticmethod
    def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = PermissionEngine._merge_dict(merged[key], value)
            else:
                merged[key] = value
        return merged

