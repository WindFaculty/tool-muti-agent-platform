from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.config import Settings
from app.core.errors import AuthError, ValidationError


@dataclass(frozen=True)
class AuthContext:
    service_token: str
    agent_id: str
    request_id: str


def authenticate_request(
    *,
    x_service_token: str | None,
    x_agent_id: str | None,
    x_request_id: str | None,
    settings: Settings,
) -> AuthContext:
    if not x_service_token:
        raise AuthError("Missing X-Service-Token")
    if not x_agent_id:
        raise AuthError("Missing X-Agent-Id")
    if not x_request_id:
        raise AuthError("Missing X-Request-Id")

    if x_service_token not in settings.service_tokens:
        raise AuthError("Invalid service token")

    validate_request_id(x_request_id)
    return AuthContext(
        service_token=x_service_token,
        agent_id=x_agent_id.strip(),
        request_id=x_request_id.strip(),
    )


def validate_request_id(value: str) -> None:
    try:
        UUID(value)
    except ValueError as exc:
        raise ValidationError("X-Request-Id must be a valid UUID") from exc

