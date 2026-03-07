from __future__ import annotations

from fastapi import Header, Request

from app.core.auth import AuthContext, authenticate_request
from app.core.config import Settings
from app.core.container import ServiceContainer


def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_auth_context(
    request: Request,
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
    x_agent_id: str | None = Header(default=None, alias="X-Agent-Id"),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
) -> AuthContext:
    settings: Settings = request.app.state.settings
    return authenticate_request(
        x_service_token=x_service_token,
        x_agent_id=x_agent_id,
        x_request_id=x_request_id,
        settings=settings,
    )

