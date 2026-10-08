from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.adapters.persistence import orm_models as _orm_models  # noqa: F401 — register with Base
from app.adapters.persistence.pg_user_repo import PostgresUserRepository
from app.api.routes import admin as admin_routes
from app.api.routes import auth, users
from app.api.routes import experts as experts_routes
from app.api.routes import jobs as jobs_routes
from app.api.routes import me as me_routes
from app.api.routes import report as report_routes
from app.api.routes import upload as upload_routes
from app.core.config import settings
from app.core.container import build as build_container
from app.core.rate_limit import limiter

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment="test" if settings.debug else "production",
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
from app.core.db import Base, SessionLocal, engine
from app.domain.user import UserRole


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        repo = PostgresUserRepository(session)
        for email in settings.expert_review_emails_list:
            await repo.get_or_create_by_email(email, UserRole.expert_review)
    app.state.container = build_container()
    yield


app = FastAPI(
    title="WallRay API",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"]
    if settings.debug
    else [o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(jobs_routes.router)
app.include_router(upload_routes.router)
app.include_router(report_routes.router)
app.include_router(admin_routes.router)
app.include_router(experts_routes.router)
app.include_router(me_routes.router)


_start_time = datetime.now(UTC).isoformat(timespec="seconds")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": _start_time}
