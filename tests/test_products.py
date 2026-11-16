import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_manager_can_create_product(client: AsyncClient, manager_headers: dict[str, str]):
    response = await client.post(
        "/api/products",
        headers=manager_headers,
        json={
            "sku": "bean-ethiopia-250",
            "name": "Cà phê Ethiopia 250g",
            "category": "Cà phê",
            "unit": "gói",
            "price_vnd": 210000,
            "stock_quantity": 12,
            "reorder_level": 4,
        },
    )
    assert response.status_code == 201
    assert response.json()["sku"] == "BEAN-ETHIOPIA-250"

    products = await client.get("/api/products?search=ETHIOPIA", headers=manager_headers)
    assert products.status_code == 200
    assert len(products.json()) == 1


async def test_staff_cannot_create_product(client: AsyncClient, staff_headers: dict[str, str]):
    response = await client.post(
        "/api/products",
        headers=staff_headers,
        json={
            "sku": "NO-PERMISSION",
            "name": "Sản phẩm bị từ chối",
            "category": "Khác",
            "unit": "cái",
            "price_vnd": 10000,
        },
    )
    assert response.status_code == 403


async def test_duplicate_sku_returns_conflict(client: AsyncClient, manager_headers: dict[str, str]):
    payload = {
        "sku": "NEW-SKU-01",
        "name": "Sản phẩm kiểm thử",
        "category": "Khác",
        "unit": "cái",
        "price_vnd": 50000,
    }
    assert (await client.post("/api/products", headers=manager_headers, json=payload)).status_code == 201
    duplicate = await client.post("/api/products", headers=manager_headers, json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_SKU"
