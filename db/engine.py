from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./database.db"
# DATABASE_URL = "postgresql://postgres:postgres@db:5432/foo"
engine = create_engine(DATABASE_URL, echo=False)

def initdb():
    """create our database models in the database"""
    SQLModel.metadata.create_all(engine)

# Dependency
def get_session():
    with Session(engine) as session:
        yield session


# DATABASE_URL = "postgresql+asyncpg://postgres:postgres@db:5432/foo"
# engine = AsyncEngine(create_engine(DATABASE_URL, echo=True, future=True))

# async def initdb():
#     """create our database models in the database"""
#     async with engine.begin() as conn:
#         # await conn.run_sync(SQLModel.metadata.drop_all)
#         await conn.run_sync(SQLModel.metadata.create_all)

# # Dependency
# async def get_session() -> AsyncSession:
#     async_session = sessionmaker(
#         engine, class_=AsyncSession, expire_on_commit=False
#     )
#     async with async_session() as session:
#         yield session
