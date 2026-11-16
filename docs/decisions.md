# Nhật ký quyết định kỹ thuật

## ADR-001 — SQLite cho bản portfolio

SQLite giúp project chạy bằng một lệnh, vẫn thể hiện được transaction, khóa ngoại, index và truy vấn SQL. Giới hạn một tiến trình ghi được ghi rõ; PostgreSQL là bước nâng cấp khi triển khai nhiều instance.

## ADR-002 — Không dùng ORM

SQL được viết trực tiếp để làm rõ transaction và quy tắc cập nhật tồn. Đổi lại, nhóm phát triển phải tự quản lý migration và mapping kết quả.

## ADR-003 — Tính tổng đơn tại server

Trình duyệt chỉ gửi `product_id` và `quantity`. Giá hiện hành, tồn khả dụng và tổng tiền đều được kiểm tra lại trong transaction để tránh sửa payload phía client.

## ADR-004 — Idempotency cho thao tác ghi quan trọng

Mạng chậm có thể khiến người dùng bấm gửi lại. `Idempotency-Key` giúp server trả lại kết quả cũ thay vì trừ kho lần hai.

## ADR-005 — Soft delete sản phẩm

Sản phẩm dùng cờ `is_active` thay vì xóa vật lý để không làm mất liên kết với lịch sử giao dịch và đơn hàng.

