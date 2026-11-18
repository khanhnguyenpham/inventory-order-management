from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.database import Database
from app.schemas import MovementCreate, OrderCreate, ProductCreate, ProductUpdate
from app.security import verify_password


class DomainError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, code: str = "BAD_REQUEST"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def authenticate(database: Database, email: str, password: str) -> dict[str, Any] | None:
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT id, email, full_name, password_hash, role
            FROM users
            WHERE email = ? COLLATE NOCASE AND is_active = 1
            """,
            (email.strip(),),
        ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    user = dict(row)
    user.pop("password_hash")
    return user


def get_user(database: Database, user_id: int) -> dict[str, Any] | None:
    with database.connect() as connection:
        row = connection.execute(
            "SELECT id, email, full_name, role FROM users WHERE id = ? AND is_active = 1",
            (user_id,),
        ).fetchone()
    return row_to_dict(row)


def list_products(
    database: Database,
    *,
    search: str = "",
    low_stock_only: bool = False,
    include_inactive: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    clauses = []
    parameters: list[Any] = []
    if not include_inactive:
        clauses.append("is_active = 1")
    if search.strip():
        clauses.append("(sku LIKE ? OR name LIKE ? OR category LIKE ?)")
        pattern = f"%{search.strip()}%"
        parameters.extend([pattern, pattern, pattern])
    if low_stock_only:
        clauses.append("stock_quantity <= reorder_level")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    parameters.extend([limit, offset])
    with database.connect() as connection:
        rows = connection.execute(
            f"""
            SELECT id, sku, name, category, unit, price_vnd, stock_quantity,
                   reorder_level, is_active, created_at, updated_at,
                   CASE WHEN stock_quantity <= reorder_level THEN 1 ELSE 0 END AS is_low_stock
            FROM products
            {where}
            ORDER BY is_low_stock DESC, name COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


def create_product(database: Database, payload: ProductCreate, actor_id: int) -> dict[str, Any]:
    with database.transaction() as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO products(sku, name, category, unit, price_vnd, stock_quantity, reorder_level)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.sku,
                    payload.name.strip(),
                    payload.category.strip(),
                    payload.unit.strip(),
                    payload.price_vnd,
                    payload.stock_quantity,
                    payload.reorder_level,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainError("Mã SKU đã tồn tại", status_code=409, code="DUPLICATE_SKU") from error
        product_id = cursor.lastrowid
        if payload.stock_quantity:
            connection.execute(
                """
                INSERT INTO stock_movements(
                    product_id, movement_type, quantity_change, stock_after,
                    reference, note, created_by
                ) VALUES (?, 'IN', ?, ?, 'INITIAL_STOCK', 'Tồn đầu khi tạo sản phẩm', ?)
                """,
                (product_id, payload.stock_quantity, payload.stock_quantity, actor_id),
            )
        _audit(
            connection,
            actor_id,
            "PRODUCT_CREATED",
            "product",
            str(product_id),
            {"sku": payload.sku},
        )
        row = connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return dict(row)


def update_product(
    database: Database,
    product_id: int,
    payload: ProductUpdate,
    actor_id: int,
) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise DomainError("Không có trường nào cần cập nhật")
    with database.transaction() as connection:
        current = connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if current is None:
            raise DomainError("Không tìm thấy sản phẩm", status_code=404, code="PRODUCT_NOT_FOUND")
        normalized = {
            key: (int(value) if isinstance(value, bool) else value.strip() if isinstance(value, str) else value)
            for key, value in changes.items()
        }
        assignments = ", ".join(f"{key} = ?" for key in normalized)
        connection.execute(
            f"UPDATE products SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [*normalized.values(), product_id],
        )
        _audit(connection, actor_id, "PRODUCT_UPDATED", "product", str(product_id), normalized)
        row = connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return dict(row)


def create_movement(
    database: Database,
    payload: MovementCreate,
    actor_id: int,
    idempotency_key: str,
) -> dict[str, Any]:
    operation = "CREATE_STOCK_MOVEMENT"
    with database.transaction() as connection:
        cached = _idempotent_response(connection, idempotency_key, operation)
        if cached is not None:
            return cached
        product = connection.execute(
            "SELECT id, sku, name, stock_quantity, is_active FROM products WHERE id = ?",
            (payload.product_id,),
        ).fetchone()
        if product is None or not product["is_active"]:
            raise DomainError("Không tìm thấy sản phẩm đang hoạt động", status_code=404, code="PRODUCT_NOT_FOUND")

        sign = 1
        if payload.movement_type == "OUT":
            sign = -1
        elif payload.movement_type == "ADJUST":
            if payload.adjustment_direction is None:
                raise DomainError("Điều chỉnh kho cần chọn hướng tăng hoặc giảm")
            sign = 1 if payload.adjustment_direction == "INCREASE" else -1
        quantity_change = sign * payload.quantity
        stock_after = product["stock_quantity"] + quantity_change
        if stock_after < 0:
            raise DomainError(
                f"Tồn kho không đủ: hiện có {product['stock_quantity']}",
                status_code=409,
                code="INSUFFICIENT_STOCK",
            )

        connection.execute(
            "UPDATE products SET stock_quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (stock_after, payload.product_id),
        )
        cursor = connection.execute(
            """
            INSERT INTO stock_movements(
                product_id, movement_type, quantity_change, stock_after,
                reference, note, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.product_id,
                payload.movement_type,
                quantity_change,
                stock_after,
                payload.reference,
                payload.note,
                actor_id,
            ),
        )
        result = {
            "movement_id": cursor.lastrowid,
            "product_id": payload.product_id,
            "sku": product["sku"],
            "quantity_change": quantity_change,
            "stock_after": stock_after,
        }
        _audit(connection, actor_id, "STOCK_CHANGED", "product", str(payload.product_id), result)
        _store_idempotent_response(connection, idempotency_key, operation, result)
    return result


def list_movements(database: Database, *, limit: int = 50) -> list[dict[str, Any]]:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT sm.id, sm.movement_type, sm.quantity_change, sm.stock_after,
                   sm.reference, sm.note, sm.created_at,
                   p.id AS product_id, p.sku, p.name AS product_name,
                   u.full_name AS created_by_name
            FROM stock_movements sm
            JOIN products p ON p.id = sm.product_id
            JOIN users u ON u.id = sm.created_by
            ORDER BY sm.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_order(
    database: Database,
    payload: OrderCreate,
    actor_id: int,
    idempotency_key: str,
) -> dict[str, Any]:
    operation = "CREATE_ORDER"
    with database.transaction() as connection:
        cached = _idempotent_response(connection, idempotency_key, operation)
        if cached is not None:
            return cached
        product_ids = [item.product_id for item in payload.items]
        placeholders = ",".join("?" for _ in product_ids)
        product_rows = connection.execute(
            f"""
            SELECT id, sku, name, price_vnd, stock_quantity
            FROM products
            WHERE is_active = 1 AND id IN ({placeholders})
            """,
            product_ids,
        ).fetchall()
        products = {row["id"]: row for row in product_rows}
        if len(products) != len(product_ids):
            raise DomainError("Đơn hàng chứa sản phẩm không tồn tại", status_code=404, code="PRODUCT_NOT_FOUND")

        total_vnd = 0
        prepared_items: list[dict[str, Any]] = []
        for item in payload.items:
            product = products[item.product_id]
            if product["stock_quantity"] < item.quantity:
                raise DomainError(
                    f"{product['name']} chỉ còn {product['stock_quantity']} sản phẩm",
                    status_code=409,
                    code="INSUFFICIENT_STOCK",
                )
            line_total = product["price_vnd"] * item.quantity
            total_vnd += line_total
            prepared_items.append(
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "quantity": item.quantity,
                    "unit_price_vnd": product["price_vnd"],
                    "line_total_vnd": line_total,
                    "stock_after": product["stock_quantity"] - item.quantity,
                }
            )

        order_code = _new_order_code()
        cursor = connection.execute(
            """
            INSERT INTO orders(order_code, customer_name, customer_phone, total_vnd, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (order_code, payload.customer_name.strip(), payload.customer_phone, total_vnd, actor_id),
        )
        order_id = cursor.lastrowid
        for item in prepared_items:
            connection.execute(
                """
                INSERT INTO order_items(
                    order_id, product_id, product_name, quantity, unit_price_vnd, line_total_vnd
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    item["product_id"],
                    item["product_name"],
                    item["quantity"],
                    item["unit_price_vnd"],
                    item["line_total_vnd"],
                ),
            )
            connection.execute(
                "UPDATE products SET stock_quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (item["stock_after"], item["product_id"]),
            )
            connection.execute(
                """
                INSERT INTO stock_movements(
                    product_id, movement_type, quantity_change, stock_after,
                    reference, note, created_by
                ) VALUES (?, 'OUT', ?, ?, ?, 'Xuất kho theo đơn hàng', ?)
                """,
                (item["product_id"], -item["quantity"], item["stock_after"], order_code, actor_id),
            )

        result = {
            "id": order_id,
            "order_code": order_code,
            "customer_name": payload.customer_name.strip(),
            "status": "CONFIRMED",
            "total_vnd": total_vnd,
            "items": prepared_items,
        }
        _audit(connection, actor_id, "ORDER_CREATED", "order", str(order_id), result)
        _store_idempotent_response(connection, idempotency_key, operation, result)
    return result


def cancel_order(database: Database, order_id: int, actor_id: int) -> dict[str, Any]:
    with database.transaction() as connection:
        order = connection.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if order is None:
            raise DomainError("Không tìm thấy đơn hàng", status_code=404, code="ORDER_NOT_FOUND")
        if order["status"] == "CANCELLED":
            raise DomainError("Đơn hàng đã được hủy trước đó", status_code=409, code="ORDER_ALREADY_CANCELLED")
        items = connection.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id = ?",
            (order_id,),
        ).fetchall()
        for item in items:
            current_stock = connection.execute(
                "SELECT stock_quantity FROM products WHERE id = ?",
                (item["product_id"],),
            ).fetchone()[0]
            stock_after = current_stock + item["quantity"]
            connection.execute(
                "UPDATE products SET stock_quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (stock_after, item["product_id"]),
            )
            connection.execute(
                """
                INSERT INTO stock_movements(
                    product_id, movement_type, quantity_change, stock_after,
                    reference, note, created_by
                ) VALUES (?, 'IN', ?, ?, ?, 'Hoàn kho do hủy đơn', ?)
                """,
                (item["product_id"], item["quantity"], stock_after, order["order_code"], actor_id),
            )
        connection.execute(
            "UPDATE orders SET status = 'CANCELLED', cancelled_at = CURRENT_TIMESTAMP WHERE id = ?",
            (order_id,),
        )
        result = {"id": order_id, "order_code": order["order_code"], "status": "CANCELLED"}
        _audit(connection, actor_id, "ORDER_CANCELLED", "order", str(order_id), result)
    return result


def list_orders(database: Database, *, limit: int = 50) -> list[dict[str, Any]]:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT o.id, o.order_code, o.customer_name, o.customer_phone, o.status,
                   o.total_vnd, o.created_at, o.cancelled_at, u.full_name AS created_by_name,
                   COUNT(oi.id) AS line_count, COALESCE(SUM(oi.quantity), 0) AS item_count
            FROM orders o
            JOIN users u ON u.id = o.created_by
            LEFT JOIN order_items oi ON oi.order_id = o.id
            GROUP BY o.id
            ORDER BY o.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def overview(database: Database) -> dict[str, Any]:
    with database.connect() as connection:
        inventory = connection.execute(
            """
            SELECT COUNT(*) AS product_count,
                   COALESCE(SUM(stock_quantity), 0) AS stock_units,
                   COALESCE(SUM(stock_quantity * price_vnd), 0) AS inventory_value_vnd,
                   SUM(CASE WHEN stock_quantity <= reorder_level THEN 1 ELSE 0 END) AS low_stock_count
            FROM products WHERE is_active = 1
            """
        ).fetchone()
        sales = connection.execute(
            """
            SELECT COUNT(*) AS order_count,
                   COALESCE(SUM(total_vnd), 0) AS revenue_vnd
            FROM orders
            WHERE status = 'CONFIRMED'
              AND date(created_at, 'localtime') = date('now', 'localtime')
            """
        ).fetchone()
        last_seven_days = connection.execute(
            """
            WITH RECURSIVE dates(day) AS (
                SELECT date('now', 'localtime', '-6 days')
                UNION ALL
                SELECT date(day, '+1 day') FROM dates WHERE day < date('now', 'localtime')
            )
            SELECT dates.day,
                   COUNT(o.id) AS order_count,
                   COALESCE(SUM(CASE WHEN o.status = 'CONFIRMED' THEN o.total_vnd ELSE 0 END), 0) AS revenue_vnd
            FROM dates
            LEFT JOIN orders o ON date(o.created_at, 'localtime') = dates.day
            GROUP BY dates.day
            ORDER BY dates.day
            """
        ).fetchall()
    return {**dict(inventory), **dict(sales), "sales_by_day": [dict(row) for row in last_seven_days]}


def list_audit_logs(database: Database, *, limit: int = 50) -> list[dict[str, Any]]:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT a.id, a.action, a.entity_type, a.entity_id, a.detail_json,
                   a.created_at, COALESCE(u.full_name, 'Hệ thống') AS actor_name
            FROM audit_logs a
            LEFT JOIN users u ON u.id = a.actor_id
            ORDER BY a.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["detail"] = json.loads(item.pop("detail_json"))
        result.append(item)
    return result


def _new_order_code() -> str:
    timestamp = datetime.now(UTC).strftime("%y%m%d%H%M%S")
    return f"DH-{timestamp}-{secrets.token_hex(3).upper()}"


def _audit(
    connection: sqlite3.Connection,
    actor_id: int,
    action: str,
    entity_type: str,
    entity_id: str,
    detail: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO audit_logs(actor_id, action, entity_type, entity_id, detail_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (actor_id, action, entity_type, entity_id, json.dumps(detail, ensure_ascii=False, default=str)),
    )


def _idempotent_response(
    connection: sqlite3.Connection,
    key: str,
    operation: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT operation, response_json FROM idempotency_keys WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    if row["operation"] != operation:
        raise DomainError(
            "Idempotency-Key đã được dùng cho thao tác khác",
            status_code=409,
            code="IDEMPOTENCY_KEY_REUSED",
        )
    return json.loads(row["response_json"])


def _store_idempotent_response(
    connection: sqlite3.Connection,
    key: str,
    operation: str,
    response: dict[str, Any],
) -> None:
    connection.execute(
        "INSERT INTO idempotency_keys(key, operation, response_json) VALUES (?, ?, ?)",
        (key, operation, json.dumps(response, ensure_ascii=False, default=str)),
    )
