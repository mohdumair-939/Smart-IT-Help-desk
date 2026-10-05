import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import jwt_secret
from app.routers import auth, dashboard, tickets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("smart_help_desk")


@asynccontextmanager
async def lifespan(_: FastAPI):
    jwt_secret()
    logger.info("Smart Help Desk API started")
    yield
    logger.info("Smart Help Desk API stopped")


app = FastAPI(
    title="Smart Help Desk API",
    version="1.0.0",
    description="Versioned API for IT help desk tickets, accounts, dashboards, and activity.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(dashboard.router)


@app.get("/api/healthz", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
