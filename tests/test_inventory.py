import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_stock_out_is_atomic_and_prevents_negative_stock(
    client: AsyncClient,
    manager_headers: dict[str, str],
):
    products = (await client.get("/api/products", headers=manager_headers)).json()
    product = next(item for item in products if item["sku"] == "SYR-VANILLA-750")
    headers = {**manager_headers, "Idempotency-Key": "movement-test-001"}
    response = await client.post(
        "/api/inventory/movements",
        headers=headers,
        json={"product_id": product["id"], "movement_type": "OUT", "quantity": 99},
    )
    assert response.status_code == 409
    refreshed = (await client.get("/api/products", headers=manager_headers)).json()
    current = next(item for item in refreshed if item["id"] == product["id"])
    assert current["stock_quantity"] == product["stock_quantity"]


async def test_repeated_idempotency_key_does_not_apply_stock_twice(
    client: AsyncClient,
    manager_headers: dict[str, str],
):
    product = (await client.get("/api/products", headers=manager_headers)).json()[0]
    headers = {**manager_headers, "Idempotency-Key": "movement-repeat-001"}
    payload = {"product_id": product["id"], "movement_type": "IN", "quantity": 5}
    first = await client.post("/api/inventory/movements", headers=headers, json=payload)
    second = await client.post("/api/inventory/movements", headers=headers, json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    refreshed = (await client.get("/api/products", headers=manager_headers)).json()
    current = next(item for item in refreshed if item["id"] == product["id"])
    assert current["stock_quantity"] == product["stock_quantity"] + 5
