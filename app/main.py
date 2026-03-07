from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.mcp import router as mcp_router
from app.api.rest import router as rest_router
from app.core.config import get_settings
from app.core.container import build_container
from app.core.errors import ToolingError


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.container = build_container(settings)
    yield


app = FastAPI(
    title="Agent Tooling Platform",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(rest_router)
app.include_router(mcp_router)


@app.exception_handler(ToolingError)
async def tooling_error_handler(_: Request, exc: ToolingError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": str(exc)}},
    )

