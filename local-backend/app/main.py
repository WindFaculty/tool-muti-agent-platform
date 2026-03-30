from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.container import build_container
from app.core.config import Settings
from app.core.logging import configure_logging, get_logger

logger = get_logger("main")


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    log_path = configure_logging(app_settings)
    stop_event = asyncio.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        container = build_container(app_settings)
        app.state.container = container
        app.state.stop_event = stop_event
        app.state.log_path = log_path
        app.state.audio_cleanup = container.speech_service.cleanup_audio_artifacts()
        logger.info("Starting backend with database at %s", container.repository.db_path)
        scheduler_task = asyncio.create_task(container.scheduler_service.run(stop_event))
        try:
            yield
        finally:
            stop_event.set()
            await asyncio.gather(scheduler_task, return_exceptions=True)
            container.repository.close()
            logger.info("Backend shutdown complete")

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


def run() -> None:
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency `uvicorn`. Run `python -m pip install -r requirements.txt` from `local-backend/`."
        ) from exc

    settings = Settings()
    uvicorn.run(
        "app.main:create_app",
        host=settings.api_host,
        port=settings.api_port,
        factory=True,
        http="h11",
        ws="websockets",
        reload=False,
    )
