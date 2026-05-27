from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .db import init_db
from .routes import router
from .services.vector_store_service import VectorStoreService


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    VectorStoreService().ensure_collection()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
app.include_router(router)
