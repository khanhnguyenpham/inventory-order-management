import pytest
from httpx import AsyncClient

from app.config import Settings
from app.main import create_app

pytestmark = pytest.mark.anyio


async def test_login_and_current_user(client: AsyncClient):
    login = await client.post(
        "/api/auth/login",
        json={"email": "quanly@demo.vn", "password": "Demo@123"},
    )
    assert login.status_code == 200
    payload = login.json()
    assert payload["user"]["role"] == "manager"

    current = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert current.status_code == 200
    assert current.json()["email"] == "quanly@demo.vn"


async def test_wrong_password_is_rejected(client: AsyncClient):
    response = await client.post(
        "/api/auth/login",
        json={"email": "quanly@demo.vn", "password": "wrong-password"},
    )
    assert response.status_code == 401


async def test_protected_endpoint_requires_token(client: AsyncClient):
    response = await client.get("/api/products")
    assert response.status_code == 401


def test_openapi_schema_can_be_generated(tmp_path):
    settings = Settings(tmp_path / "openapi.db", "test-secret", 60, "test")
    schema = create_app(settings).openapi()
    assert schema["info"]["title"] == "API quản lý tồn kho và đơn hàng"
    assert "/api/orders" in schema["paths"]
