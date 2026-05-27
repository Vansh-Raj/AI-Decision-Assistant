from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .db import init_db
from .observability import ObservabilityMiddleware, configure_logging, get_logger, log_event
from .routes import router
from .services.vector_store_service import VectorStoreService


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger = get_logger("startup")
    log_event(logger, "application_starting", version=settings.app_version)
    init_db()
    VectorStoreService().ensure_collection()
    log_event(logger, "application_ready", vector_collection=settings.qdrant_collection_name)
    yield


configure_logging(settings.log_level)
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
app.add_middleware(ObservabilityMiddleware)
app.include_router(router)
