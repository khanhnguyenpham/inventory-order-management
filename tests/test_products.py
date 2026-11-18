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


async def test_product_list_supports_pagination(client: AsyncClient, manager_headers: dict[str, str]):
    first_page = await client.get("/api/products?limit=2", headers=manager_headers)
    second_page = await client.get("/api/products?limit=2&offset=2", headers=manager_headers)

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert len(first_page.json()) == 2
    assert len(second_page.json()) == 2
    assert {item["id"] for item in first_page.json()}.isdisjoint({item["id"] for item in second_page.json()})


async def test_product_pagination_rejects_invalid_values(client: AsyncClient, manager_headers: dict[str, str]):
    assert (await client.get("/api/products?limit=0", headers=manager_headers)).status_code == 422
    assert (await client.get("/api/products?offset=-1", headers=manager_headers)).status_code == 422
