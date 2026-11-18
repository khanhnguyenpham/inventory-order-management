# Roadmap

Kho Gọn hiện đã đủ để trình bày năng lực Python backend ở mức portfolio. Những mục dưới đây là hướng nâng cấp nếu tiếp tục phát triển, không phải tính năng đã hoàn thành.

## Ưu tiên gần

### PostgreSQL và migration

- Thay SQLite bằng PostgreSQL cho môi trường nhiều instance.
- Quản lý thay đổi schema bằng migration có thể rollback.
- Chạy lại toàn bộ test transaction và idempotency trên PostgreSQL.

### Vòng đời tài khoản

- Quy trình tạo tài khoản bởi quản lý.
- Đổi/quên mật khẩu và vô hiệu hóa phiên đăng nhập.
- Rate limit cho đăng nhập và audit các lần thất bại.

### Quan sát vận hành

- Request ID xuyên suốt API và audit log.
- Structured logging, thống kê lỗi và cảnh báo health check.
- Tách readiness khỏi liveness khi có database ngoài.

## Chỉ làm khi có nhu cầu thật

- Đa chi nhánh và chuyển kho.
- Nhập hàng theo nhà cung cấp.
- Hóa đơn, thanh toán và hoàn tiền.

Các mục này cần yêu cầu nghiệp vụ rõ ràng; không thêm chỉ để tăng số lượng tính năng.

