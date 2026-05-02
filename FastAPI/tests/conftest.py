import asyncio
import sys
import os
from collections.abc import AsyncGenerator

# 1. WINDOWS LOOP FIX: Must be at the very top
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import boto3
import pytest
from httpx import ASGITransport, AsyncClient
from moto import mock_aws
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# 2. Environment Setup
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["S3_BUCKET_NAME"] = "test-bucket"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["S3_ACCESS_KEY_ID"] = "testing"
os.environ["S3_SECRET_ACCESS_KEY"] = "testing"
os.environ["S3_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

from database import Base, get_db
from main import app

pytest_plugins = ["anyio"]

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="session")
def test_engine():
    return create_async_engine(
        os.environ["DATABASE_URL"],
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

@pytest.fixture(scope="session")
async def setup_database(test_engine):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()

@pytest.fixture
async def db_session(test_engine, setup_database) -> AsyncGenerator[AsyncSession, None]:
    connection = await test_engine.connect()
    transaction = await connection.begin()
    
    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
            await connection.close()

@pytest.fixture
def mocked_aws():
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=os.environ["S3_BUCKET_NAME"])
        yield s3

@pytest.fixture
async def client(db_session: AsyncSession, mocked_aws) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # transport=ASGITransport(app=app) ensures we test the app directly without a real network
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

# --- Robust Helper Functions ---

async def create_test_user(client: AsyncClient, username="testuser", email="test@example.com", password="testpassword123"):
    """Helper to create a user. Handles potential 404/422 errors gracefully."""
    response = await client.post("/api/users", json={
        "username": username,
        "email": email,
        "password": password
    })
    # If /api/users fails with 404, try /api/users/ (common trailing slash issue)
    if response.status_code == 404:
        response = await client.post("/api/users/", json={
            "username": username,
            "email": email,
            "password": password
        })
    return response

async def login_user(client: AsyncClient, email="test@example.com", password="testpassword123"):
    """Helper to login. Includes error checking to prevent KeyError: 'access_token'."""
    response = await client.post("/api/users/token", data={
        "username": email,
        "password": password
    })
    # Fallback for trailing slash
    if response.status_code == 404:
        response = await client.post("/api/users/token/", data={
            "username": email,
            "password": password
        })
        
    if response.status_code != 200:
        raise RuntimeError(f"Login failed with status {response.status_code}: {response.text}")
        
    data = response.json()
    return data["access_token"]

def auth_header(token: str):
    return {"Authorization": f"Bearer {token}"}
