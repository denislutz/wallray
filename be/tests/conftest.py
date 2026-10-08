from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.api.deps import get_email, get_renderer, get_session, get_storage, get_vision_llm
from app.core.db import Base
from app.core.rate_limit import limiter
from app.main import app
from tests.fakes import EmailFake, RendererStub, StorageFake, VisionLLMStub


@pytest.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def storage_fake() -> StorageFake:
    return StorageFake()


@pytest.fixture
async def client(db_engine: AsyncEngine, storage_fake: StorageFake) -> AsyncGenerator[AsyncClient]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _get_session() -> AsyncGenerator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_storage] = lambda: storage_fake
    app.dependency_overrides[get_vision_llm] = lambda: VisionLLMStub()
    app.dependency_overrides[get_renderer] = lambda: RendererStub()
    app.dependency_overrides[get_email] = lambda: EmailFake()
    # Fresh rate-limit counters per test — the limiter's in-memory storage otherwise persists
    # across tests within the same run, since it's a module-level singleton.
    limiter.reset()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_storage, None)
    app.dependency_overrides.pop(get_vision_llm, None)
    app.dependency_overrides.pop(get_renderer, None)
    app.dependency_overrides.pop(get_email, None)


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Exposes a raw session into the same in-memory DB used by the client fixture."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


# assess_client is now identical to client — kept as alias for existing test references
@pytest.fixture
async def assess_client(db_engine: AsyncEngine) -> AsyncGenerator[AsyncClient]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    storage = StorageFake()

    async def _get_session() -> AsyncGenerator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_vision_llm] = lambda: VisionLLMStub()
    app.dependency_overrides[get_renderer] = lambda: RendererStub()
    app.dependency_overrides[get_email] = lambda: EmailFake()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_storage, None)
    app.dependency_overrides.pop(get_vision_llm, None)
    app.dependency_overrides.pop(get_renderer, None)
    app.dependency_overrides.pop(get_email, None)
