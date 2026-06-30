# File Path: backend/app/main.py
# Timestamp: 2026-05-26T21:20:00+08:00
# Version: v0.3

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.asset_contracts import router as asset_contracts_router
from app.api.routers.assistant import router as assistant_router
from app.api.routers.ai_accounts import router as ai_accounts_router
from app.api.routers.analytics import router as analytics_router
from app.api.routers.api_keys import router as api_keys_router
from app.api.routers.approvals import router as approvals_router
from app.api.routers.auth import router as auth_router
from app.api.routers.costs import router as costs_router
from app.api.routers.dashboard import router as dashboard_router
from app.api.routers.departments import router as departments_router
from app.api.routers.exports import router as exports_router
from app.api.routers.gateway import provider_client, router as gateway_router
from app.api.routers.lava import router as lava_router
from app.api.routers.models import router as models_router
from app.api.routers.my import router as my_router
from app.api.routers.ops import router as ops_router
from app.api.routers.projects import router as projects_router
from app.api.routers.resource_limits import router as resource_limits_router
from app.api.routers.resource_usage_events import router as resource_usage_events_router
from app.api.routers.usage_purposes import router as usage_purposes_router
from app.api.routers.usage import router as usage_router
from app.api.routers.users import router as users_router
from app.api.routers.work_outputs import router as work_outputs_router
from app.core.config import get_settings
from app.db.init_db import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield
    await provider_client.close()


app = FastAPI(
    title="LLM FinOps V1.1",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz", tags=["health"])
def healthz() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@app.get("/", tags=["health"])
def root() -> dict:
    return {
        "message": "LLM FinOps API is running",
        "docs": "/docs",
        "healthz": "/healthz",
        "frontend": "http://localhost:5173",
    }


app.include_router(auth_router)
app.include_router(my_router)
app.include_router(dashboard_router)
app.include_router(users_router)
app.include_router(departments_router)
app.include_router(projects_router)
app.include_router(api_keys_router)
app.include_router(ai_accounts_router)
app.include_router(asset_contracts_router)
app.include_router(models_router)
app.include_router(usage_router)
app.include_router(resource_usage_events_router)
app.include_router(usage_purposes_router)
app.include_router(work_outputs_router)
app.include_router(costs_router)
app.include_router(resource_limits_router)
app.include_router(analytics_router)
app.include_router(approvals_router)
app.include_router(exports_router)
app.include_router(gateway_router)
app.include_router(ops_router)
app.include_router(lava_router)
app.include_router(assistant_router)
