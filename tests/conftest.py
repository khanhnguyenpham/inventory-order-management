from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.database import Database
from app.main import create_app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(tmp_path: Path):
    settings = Settings(
        database_path=tmp_path / "test.db",
        token_secret="test-secret-only",
        token_ttl_minutes=60,
        environment="test",
    )
    Database(settings.database_path).initialize()
    application = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
async def manager_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/auth/login",
        json={"email": "quanly@demo.vn", "password": "Demo@123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def staff_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/auth/login",
        json={"email": "nhanvien@demo.vn", "password": "Demo@123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
