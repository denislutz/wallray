import asyncio

import app.adapters.persistence.orm_models as _  # noqa: F401 — registers tables with Base.metadata
from app.core.db import Base, engine


async def reset() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


asyncio.run(reset())
