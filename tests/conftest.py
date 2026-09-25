import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import db.county_models  # noqa: F401  (registers the new tables with SQLModel.metadata)
from db.engine import get_session
from main import app


def _engine_url(tmp_path) -> str:
    """Postgres when TEST_DATABASE_URL is set (CI), else a throwaway SQLite file.

    A file rather than :memory: so several connections share one database.
    """
    return os.getenv("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path}/test.db"


@pytest.fixture
async def db_engine(tmp_path):
    engine = create_async_engine(_engine_url(tmp_path))
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def session(db_engine):
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as s:
        yield s


@pytest.fixture
async def client(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
