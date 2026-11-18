# Kho Gọn — quản lý tồn kho và đơn hàng

Ứng dụng web tiếng Việt dành cho cửa hàng nhỏ cần theo dõi nhập – xuất, tạo đơn bán hàng và nhận diện sản phẩm sắp hết. Project tập trung vào năng lực **Python backend**: thiết kế API, giao dịch cơ sở dữ liệu, xác thực, phân quyền, kiểm thử và triển khai.

> Đây là ứng dụng web portfolio sử dụng dữ liệu mẫu. Không đại diện cho một cửa hàng hoặc doanh nghiệp thật.

## Vị trí trong portfolio

Kho Gọn là project tôi dùng để chứng minh năng lực **lập trình Python backend** sau phần phân tích dữ liệu: API không chỉ trả dữ liệu mà còn phải giữ đúng quy tắc nghiệp vụ khi request lỗi, gửi lặp hoặc nhiều sản phẩm thay đổi cùng lúc. Hai mảnh ghép còn lại là [phân tích vận hành](https://github.com/khanhnguyenpham/outpatient-operations-analysis) và [AI Systems](https://github.com/khanhnguyenpham/hospital-appointment-risk-system).

Xem [lịch phát triển](CHANGELOG.md), [roadmap](ROADMAP.md) và [hành trình học tập 2022–2026](https://github.com/khanhnguyenpham).

## Dùng trực tuyến

- Ứng dụng: [https://kho-gon.onrender.com](https://kho-gon.onrender.com)
- OpenAPI: [https://kho-gon.onrender.com/docs](https://kho-gon.onrender.com/docs)
- Health check: [https://kho-gon.onrender.com/health](https://kho-gon.onrender.com/health)

Render Free có thể tạm dừng dịch vụ khi không có truy cập; lần mở đầu tiên đôi khi cần chờ khoảng 30–60 giây. Dữ liệu SQLite trên bản trực tuyến là dữ liệu mẫu và có thể được khởi tạo lại sau khi dịch vụ được triển khai lại.

## Vấn đề nghiệp vụ

Khi tồn kho và đơn hàng được ghi ở nhiều bảng tính, một lần gửi form lặp hoặc một đơn thất bại giữa chừng có thể khiến số lượng tồn không còn khớp. Kho Gọn xử lý các rủi ro đó bằng những quy tắc rõ ràng:

- Mọi thao tác xuất kho và tạo đơn chạy trong transaction SQLite.
- Không cho phép tồn kho âm.
- Đơn tạo lỗi không làm thay đổi bất kỳ sản phẩm nào.
- `Idempotency-Key` ngăn cùng một request nhập/xuất hoặc tạo đơn bị áp dụng hai lần.
- Hủy đơn hoàn lại đúng số lượng và tạo lịch sử nhập kho tương ứng.
- Thay đổi quan trọng được ghi vào audit log.

## Chức năng

- Đăng nhập bằng token HMAC-SHA256, mật khẩu băm PBKDF2.
- Phân quyền `manager` và `staff`.
- Danh mục sản phẩm, SKU, giá bán, tồn kho và ngưỡng đặt lại.
- Nhập, xuất và điều chỉnh kho.
- Tạo đơn nhiều sản phẩm, kiểm tra tồn và tính tổng tại server.
- Hủy đơn và hoàn kho dành cho quản lý.
- Dashboard doanh thu, giá trị tồn và cảnh báo tồn thấp.
- Nhật ký hệ thống và Swagger UI tại `/docs`.
- Giao diện responsive, toàn bộ dữ liệu lấy từ API thật.

## Tài khoản dùng thử

| Vai trò | Email | Mật khẩu |
|---|---|---|
| Quản lý | `quanly@demo.vn` | `Demo@123` |
| Nhân viên | `nhanvien@demo.vn` | `Demo@123` |

Các tài khoản dùng thử giúp nhà tuyển dụng kiểm tra đầy đủ luồng nghiệp vụ. Môi trường vận hành thực tế phải có quy trình tạo người dùng và thay đổi mật khẩu riêng.

## Kiến trúc

```text
Trình duyệt
   │  JSON / Bearer token
   ▼
FastAPI ── xác thực + phân quyền ── dịch vụ nghiệp vụ
                                           │
                                           ▼
                                      SQLite (WAL)
                         sản phẩm · đơn hàng · dòng kho · audit
```

Chi tiết nằm trong [tài liệu kiến trúc](docs/architecture.md), [mô hình dữ liệu](docs/data_model.md) và [nhật ký quyết định](docs/decisions.md).

## Chạy trên máy cá nhân

Yêu cầu Python 3.11–3.13. Python 3.14 trên một số bản Windows hiện có vấn đề event loop; Docker hoặc WSL là lựa chọn ổn định nếu gặp lỗi này.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Mở `http://127.0.0.1:8000`. Cơ sở dữ liệu mẫu được tạo tại `data/inventory.db` trong lần chạy đầu tiên.

### Chạy bằng Docker

```bash
docker build -t kho-gon .
docker run --rm -p 8000:8000 -e APP_TOKEN_SECRET=replace-with-a-long-random-secret kho-gon
```

## Kiểm thử

```bash
ruff format --check .
ruff check .
python -m pytest
```

Bộ test bao phủ đăng nhập, phân quyền, SKU trùng, rollback giao dịch, chống tồn âm, idempotency, hoàn kho khi hủy đơn, audit log và khả năng sinh OpenAPI schema.

## API chính

| Method | Endpoint | Mục đích |
|---|---|---|
| `POST` | `/api/auth/login` | Đăng nhập |
| `GET/POST` | `/api/products` | Tra cứu hoặc tạo sản phẩm |
| `POST` | `/api/inventory/movements` | Nhập, xuất hoặc điều chỉnh |
| `GET/POST` | `/api/orders` | Tra cứu hoặc tạo đơn |
| `POST` | `/api/orders/{id}/cancel` | Hủy đơn và hoàn kho |
| `GET` | `/api/reports/overview` | KPI dashboard |
| `GET` | `/api/audit-logs` | Nhật ký quản trị |

Các endpoint làm thay đổi tồn kho yêu cầu header `Idempotency-Key` dài 8–100 ký tự.

`GET /api/products` hỗ trợ `search`, `low_stock_only`, `include_inactive`, `limit` và `offset`. `limit` nằm trong khoảng 1–500; phân trang được xử lý tại database thay vì tải toàn bộ danh mục về trình duyệt.

## Giới hạn có chủ đích

- SQLite phù hợp bản portfolio hoặc một tiến trình ứng dụng; khi mở rộng nhiều instance nên chuyển sang PostgreSQL.
- Dữ liệu trên gói hosting miễn phí có thể bị đặt lại khi dịch vụ khởi động lại.
- Chưa có thanh toán, hóa đơn điện tử, đa chi nhánh hoặc quy trình quên mật khẩu.
- Doanh thu trong dashboard là giá trị đơn xác nhận, chưa trừ chi phí hoặc hoàn tiền.

## Công nghệ

Python · FastAPI · Pydantic · SQLite · HTML/CSS/JavaScript · Pytest · Ruff · Docker · GitHub Actions

