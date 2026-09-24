import os
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

_DB_PATH = Path(__file__).parent.parent.parent / "database.db"
# Overridable via DATABASE_URL so the container can point at a mounted volume,
# e.g. sqlite+aiosqlite:////data/realestate.db (default: repo-local database.db).
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{_DB_PATH}")
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

async def init_db():
    """create our database models in the database"""
    async with engine.begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)

# Dependency
async def get_session() -> AsyncSession:
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
