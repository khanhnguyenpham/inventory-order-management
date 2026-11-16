# Hướng dẫn bảo trì

- Giao diện và tài liệu hướng đến người dùng phải viết bằng tiếng Việt rõ ràng.
- Không bỏ qua transaction khi thay đổi tồn kho hoặc trạng thái đơn hàng.
- Không nhận giá bán hoặc tổng đơn từ client; luôn đọc lại từ database.
- Mọi endpoint ghi có thể bị gửi lặp; giữ idempotency cho tạo đơn và giao dịch kho.
- Thêm test cho mọi thay đổi quy tắc nghiệp vụ hoặc phân quyền.
- Không commit database, token secret, dữ liệu người dùng thật hoặc file môi trường.

