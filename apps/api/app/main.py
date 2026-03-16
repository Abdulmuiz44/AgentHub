from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import catalog, health, providers, runs, sessions
from app.config import settings
from app.db.session import init_db
from app.services.worker import RunWorker


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    worker = RunWorker()
    worker.start()
    app.state.run_worker = worker
    try:
        yield
    finally:
        worker.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(runs.router)
app.include_router(providers.router)
app.include_router(catalog.router)
