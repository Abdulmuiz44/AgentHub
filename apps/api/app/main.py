from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import catalog, health, providers, runs, sessions
from app.config import settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(runs.router)
app.include_router(providers.router)
app.include_router(catalog.router)
