from __future__ import annotations

import re
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key\s*[:=]\s*)([^\s]+)", re.IGNORECASE),
    re.compile(r"(bearer\s+)([A-Za-z0-9._\-]+)", re.IGNORECASE),
    re.compile(r"(token\s*[:=]\s*)([^\s]+)", re.IGNORECASE),
]


def redact_text(text: str, secrets: list[str] | None = None) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    for secret in secrets or []:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def redact_mapping(value: Any, secrets: list[str] | None = None) -> Any:
    if isinstance(value, str):
        return redact_text(value, secrets)
    if isinstance(value, list):
        return [redact_mapping(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: redact_mapping(item, secrets) for key, item in value.items()}
    return value
