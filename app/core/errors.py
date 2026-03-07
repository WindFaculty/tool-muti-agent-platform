from __future__ import annotations


class ToolingError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class AuthError(ToolingError):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__("AUTH_ERROR", message, 401)


class PermissionDeniedError(ToolingError):
    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__("PERMISSION_DENIED", message, 403)


class ValidationError(ToolingError):
    def __init__(self, message: str = "Invalid input") -> None:
        super().__init__("VALIDATION_ERROR", message, 400)


class ToolNotFoundError(ToolingError):
    def __init__(self, tool_name: str) -> None:
        super().__init__("TOOL_NOT_FOUND", f"Tool '{tool_name}' was not found", 404)


class RateLimitError(ToolingError):
    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__("RATE_LIMIT_EXCEEDED", message, 429)


class ConfigurationError(ToolingError):
    def __init__(self, message: str) -> None:
        super().__init__("CONFIGURATION_ERROR", message, 500)


class ExecutionError(ToolingError):
    def __init__(self, message: str) -> None:
        super().__init__("EXECUTION_ERROR", message, 500)

