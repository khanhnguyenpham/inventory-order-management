from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=8, max_length=128)


class ProductCreate(BaseModel):
    sku: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9-]+$")
    name: str = Field(min_length=3, max_length=160)
    category: str = Field(min_length=2, max_length=80)
    unit: str = Field(min_length=1, max_length=30)
    price_vnd: int = Field(ge=0, le=1_000_000_000)
    stock_quantity: int = Field(default=0, ge=0, le=10_000_000)
    reorder_level: int = Field(default=0, ge=0, le=10_000_000)

    @field_validator("sku")
    @classmethod
    def uppercase_sku(cls, value: str) -> str:
        return value.strip().upper()


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=160)
    category: str | None = Field(default=None, min_length=2, max_length=80)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    price_vnd: int | None = Field(default=None, ge=0, le=1_000_000_000)
    reorder_level: int | None = Field(default=None, ge=0, le=10_000_000)
    is_active: bool | None = None


class MovementCreate(BaseModel):
    product_id: int = Field(gt=0)
    movement_type: str = Field(pattern=r"^(IN|OUT|ADJUST)$")
    quantity: int = Field(gt=0, le=10_000_000)
    adjustment_direction: str | None = Field(default=None, pattern=r"^(INCREASE|DECREASE)$")
    reference: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=300)


class OrderLineCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100_000)


class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    customer_phone: str | None = Field(default=None, max_length=30, pattern=r"^[0-9+ .-]*$")
    items: list[OrderLineCreate] = Field(min_length=1, max_length=50)

    @field_validator("items")
    @classmethod
    def unique_products(cls, items: list[OrderLineCreate]) -> list[OrderLineCreate]:
        product_ids = [item.product_id for item in items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Mỗi sản phẩm chỉ được xuất hiện một lần trong đơn hàng")
        return items
