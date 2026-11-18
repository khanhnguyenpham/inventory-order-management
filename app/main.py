import re
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.database import Database
from app.schemas import LoginRequest, MovementCreate, OrderCreate, ProductCreate, ProductUpdate
from app.security import create_token, decode_token
from app.services import (
    DomainError,
    authenticate,
    cancel_order,
    create_movement,
    create_order,
    create_product,
    get_user,
    list_audit_logs,
    list_movements,
    list_orders,
    list_products,
    overview,
    update_product,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,100}$")
bearer_scheme = HTTPBearer(auto_error=False)


def create_app(settings: Settings | None = None, *, seed_demo: bool = True) -> FastAPI:
    actual_settings = settings or get_settings()
    database = Database(actual_settings.database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.initialize(seed_demo=seed_demo)
        yield

    application = FastAPI(
        title="API quản lý tồn kho và đơn hàng",
        version="1.0.0",
        description="API minh họa nghiệp vụ nhập, xuất, bán hàng và kiểm soát tồn kho.",
        lifespan=lifespan,
    )
    application.state.database = database
    application.state.settings = actual_settings

    @application.exception_handler(DomainError)
    async def handle_domain_error(_: Request, error: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )

    async def current_user(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    ) -> dict[str, Any]:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cần đăng nhập")
        try:
            payload = decode_token(credentials.credentials, actual_settings.token_secret)
            user = get_user(database, int(payload["sub"]))
        except (ValueError, TypeError):
            user = None
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập không hợp lệ")
        return user

    def require_role(role: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        async def dependency(user: Annotated[dict[str, Any], Depends(current_user)]) -> dict[str, Any]:
            if user["role"] != role:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền thực hiện")
            return user

        return dependency

    async def validated_idempotency_key(
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> str:
        if idempotency_key is None or not IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Idempotency-Key phải dài 8-100 ký tự và chỉ chứa chữ, số, . _ : -",
            )
        return idempotency_key

    @application.get("/health", tags=["Hệ thống"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": actual_settings.environment}

    @application.post("/api/auth/login", tags=["Xác thực"])
    async def login(payload: LoginRequest) -> dict[str, Any]:
        user = authenticate(database, payload.email, payload.password)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email hoặc mật khẩu không đúng")
        token = create_token(
            str(user["id"]),
            user["role"],
            actual_settings.token_secret,
            actual_settings.token_ttl_minutes,
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in_minutes": actual_settings.token_ttl_minutes,
            "user": user,
        }

    @application.get("/api/auth/me", tags=["Xác thực"])
    async def me(user: Annotated[dict[str, Any], Depends(current_user)]) -> dict[str, Any]:
        return user

    @application.get("/api/products", tags=["Sản phẩm"])
    async def products(
        _: Annotated[dict[str, Any], Depends(current_user)],
        search: str = Query(default="", max_length=100),
        low_stock_only: bool = False,
        include_inactive: bool = False,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        return list_products(
            database,
            search=search,
            low_stock_only=low_stock_only,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
        )

    @application.post("/api/products", status_code=status.HTTP_201_CREATED, tags=["Sản phẩm"])
    async def add_product(
        payload: ProductCreate,
        user: Annotated[dict[str, Any], Depends(require_role("manager"))],
    ) -> dict[str, Any]:
        return create_product(database, payload, user["id"])

    @application.patch("/api/products/{product_id}", tags=["Sản phẩm"])
    async def edit_product(
        product_id: int,
        payload: ProductUpdate,
        user: Annotated[dict[str, Any], Depends(require_role("manager"))],
    ) -> dict[str, Any]:
        return update_product(database, product_id, payload, user["id"])

    @application.get("/api/inventory/movements", tags=["Kho"])
    async def movements(
        _: Annotated[dict[str, Any], Depends(current_user)],
        limit: int = Query(default=50, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        return list_movements(database, limit=limit)

    @application.post("/api/inventory/movements", status_code=status.HTTP_201_CREATED, tags=["Kho"])
    async def add_movement(
        payload: MovementCreate,
        user: Annotated[dict[str, Any], Depends(current_user)],
        idempotency_key: Annotated[str, Depends(validated_idempotency_key)],
    ) -> dict[str, Any]:
        return create_movement(database, payload, user["id"], idempotency_key)

    @application.get("/api/orders", tags=["Đơn hàng"])
    async def orders(
        _: Annotated[dict[str, Any], Depends(current_user)],
        limit: int = Query(default=50, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        return list_orders(database, limit=limit)

    @application.post("/api/orders", status_code=status.HTTP_201_CREATED, tags=["Đơn hàng"])
    async def add_order(
        payload: OrderCreate,
        user: Annotated[dict[str, Any], Depends(current_user)],
        idempotency_key: Annotated[str, Depends(validated_idempotency_key)],
    ) -> dict[str, Any]:
        return create_order(database, payload, user["id"], idempotency_key)

    @application.post("/api/orders/{order_id}/cancel", tags=["Đơn hàng"])
    async def remove_order(
        order_id: int,
        user: Annotated[dict[str, Any], Depends(require_role("manager"))],
    ) -> dict[str, Any]:
        return cancel_order(database, order_id, user["id"])

    @application.get("/api/reports/overview", tags=["Báo cáo"])
    async def report(_: Annotated[dict[str, Any], Depends(current_user)]) -> dict[str, Any]:
        return overview(database)

    @application.get("/api/audit-logs", tags=["Kiểm soát"])
    async def audit_logs(
        _: Annotated[dict[str, Any], Depends(require_role("manager"))],
        limit: int = Query(default=50, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        return list_audit_logs(database, limit=limit)

    application.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @application.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return application


app = create_app()
