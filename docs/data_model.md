# Mô hình dữ liệu

| Bảng | Vai trò | Ràng buộc chính |
|---|---|---|
| `users` | Tài khoản quản lý/nhân viên | Email duy nhất, role hợp lệ |
| `products` | Danh mục và tồn hiện tại | SKU duy nhất, tồn không âm |
| `stock_movements` | Sổ thay đổi tồn kho | Lưu thay đổi và tồn sau giao dịch |
| `orders` | Phần đầu đơn bán | Mã đơn duy nhất, trạng thái xác nhận/hủy |
| `order_items` | Sản phẩm trong đơn | Số lượng dương, snapshot tên và giá |
| `audit_logs` | Dấu vết nghiệp vụ | Actor, hành động, đối tượng, chi tiết JSON |
| `idempotency_keys` | Chống áp dụng request lặp | Key duy nhất theo thao tác |

## Quy tắc đối soát

- `products.stock_quantity` không được âm.
- Mỗi lần đổi tồn tạo đúng một `stock_movements` cho sản phẩm tương ứng.
- Tổng đơn bằng tổng `quantity × unit_price_vnd` của các dòng.
- Đơn đã hủy không được hủy lần hai.
- `order_items` giữ snapshot tên và giá để lịch sử không đổi khi danh mục được cập nhật.

