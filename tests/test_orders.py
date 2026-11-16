import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_create_order_decrements_stock_and_cancel_restores_it(
    client: AsyncClient,
    manager_headers: dict[str, str],
):
    product = (await client.get("/api/products", headers=manager_headers)).json()[0]
    create_headers = {**manager_headers, "Idempotency-Key": "order-create-001"}
    created = await client.post(
        "/api/orders",
        headers=create_headers,
        json={
            "customer_name": "Khách kiểm thử",
            "customer_phone": "0900000000",
            "items": [{"product_id": product["id"], "quantity": 2}],
        },
    )
    assert created.status_code == 201
    assert created.json()["total_vnd"] == product["price_vnd"] * 2

    overview = await client.get("/api/reports/overview", headers=manager_headers)
    assert overview.json()["order_count"] == 1
    assert overview.json()["revenue_vnd"] == product["price_vnd"] * 2

    after_order = (await client.get("/api/products", headers=manager_headers)).json()
    current = next(item for item in after_order if item["id"] == product["id"])
    assert current["stock_quantity"] == product["stock_quantity"] - 2

    cancelled = await client.post(f"/api/orders/{created.json()['id']}/cancel", headers=manager_headers)
    assert cancelled.status_code == 200
    after_cancel = (await client.get("/api/products", headers=manager_headers)).json()
    restored = next(item for item in after_cancel if item["id"] == product["id"])
    assert restored["stock_quantity"] == product["stock_quantity"]


async def test_order_failure_does_not_change_any_product(
    client: AsyncClient,
    staff_headers: dict[str, str],
):
    products = (await client.get("/api/products", headers=staff_headers)).json()
    first, second = products[:2]
    response = await client.post(
        "/api/orders",
        headers={**staff_headers, "Idempotency-Key": "order-rollback-001"},
        json={
            "customer_name": "Khách kiểm thử",
            "items": [
                {"product_id": first["id"], "quantity": 1},
                {"product_id": second["id"], "quantity": second["stock_quantity"] + 1},
            ],
        },
    )
    assert response.status_code == 409
    refreshed = (await client.get("/api/products", headers=staff_headers)).json()
    current_first = next(item for item in refreshed if item["id"] == first["id"])
    assert current_first["stock_quantity"] == first["stock_quantity"]


async def test_audit_log_records_business_actions(client: AsyncClient, manager_headers: dict[str, str]):
    product = (await client.get("/api/products", headers=manager_headers)).json()[0]
    await client.post(
        "/api/inventory/movements",
        headers={**manager_headers, "Idempotency-Key": "audit-movement-001"},
        json={"product_id": product["id"], "movement_type": "IN", "quantity": 3},
    )
    audit = await client.get("/api/audit-logs", headers=manager_headers)
    assert audit.status_code == 200
    assert audit.json()[0]["action"] == "STOCK_CHANGED"
