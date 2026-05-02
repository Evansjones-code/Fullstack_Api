from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

# pool_pre_ping: Fixes "SSL connection closed unexpectedly" by testing connections
# pool_recycle: Prevents stale connections by refreshing them every 5 minutes
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"sslmode": "require"}
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            # Ensures the session is closed even if an error occurs
            await session.close()
