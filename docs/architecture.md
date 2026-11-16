# Kiến trúc hệ thống

## Mục tiêu

Hệ thống ưu tiên tính đúng của tồn kho và khả năng truy vết hơn số lượng tính năng. Một request thất bại không được để lại trạng thái nửa chừng.

## Các lớp

1. **Giao diện:** HTML/CSS/JavaScript thuần, gọi API cùng origin và không chứa dữ liệu nghiệp vụ viết cứng.
2. **API:** FastAPI xử lý HTTP, xác thực, phân quyền và kiểm tra input qua Pydantic.
3. **Dịch vụ:** `app/services.py` chứa quy tắc tạo đơn, cập nhật tồn, hoàn kho và audit.
4. **Dữ liệu:** SQLite bật foreign key, WAL, busy timeout và `BEGIN IMMEDIATE` cho giao dịch ghi.

## Luồng tạo đơn

```text
Request + Idempotency-Key
        │
        ├─ kiểm tra key đã xử lý chưa
        ├─ đọc toàn bộ sản phẩm trong một transaction
        ├─ xác nhận sản phẩm hoạt động và đủ tồn
        ├─ tạo order + order_items
        ├─ trừ tồn + tạo stock_movements
        ├─ ghi audit_log
        └─ lưu response theo Idempotency-Key rồi commit
```

Nếu bất kỳ bước nào lỗi, transaction rollback toàn bộ.

## Ranh giới bảo mật

- Mật khẩu không lưu dạng rõ; PBKDF2-SHA256 dùng salt ngẫu nhiên và 240.000 vòng.
- Token được ký HMAC-SHA256, có `iat`, `exp`, vai trò và thời hạn mặc định tám giờ.
- Môi trường production từ chối khởi động nếu vẫn dùng secret mặc định.
- Giá bán và tổng đơn được tính lại tại server; không tin giá trị gửi từ trình duyệt.
- Chỉ quản lý được tạo/sửa sản phẩm, hủy đơn và xem audit log.

## Hướng mở rộng

- PostgreSQL và migration Alembic khi chạy nhiều instance.
- Refresh token, thu hồi phiên và quy trình quản lý người dùng.
- Outbox/event queue khi tích hợp kế toán hoặc giao vận.
- Metrics, structured logging và cảnh báo lỗi production.

