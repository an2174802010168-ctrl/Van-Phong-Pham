# FlaskShop – Web bán hàng bằng Flask

Web bán hàng cơ bản, viết theo kiến trúc **application factory + blueprint** giống `microblog`/`flasky`
(Flask 3, Flask-SQLAlchemy 3.1 kiểu SQLAlchemy 2.0, Flask-Login, Flask-WTF, Flask-Migrate, SQLite).

## Chức năng

**Khách hàng**
- Xem danh sách sản phẩm: tìm kiếm, lọc theo danh mục, sắp xếp (mới nhất / giá / tên), phân trang
- Trang chi tiết sản phẩm, gợi ý sản phẩm cùng danh mục
- Giỏ hàng (lưu trong session – khách chưa đăng nhập vẫn thêm được), tự giới hạn theo tồn kho
- Đăng ký / đăng nhập / đăng xuất
- Đặt hàng (COD), phí ship 30.000₫, **miễn phí cho đơn từ 500.000₫**
- Xem lịch sử đơn, chi tiết đơn, tự huỷ đơn khi còn "Chờ xác nhận" (tồn kho được hoàn lại)

**Quản trị (`/admin`)**
- Tổng quan: doanh thu, số đơn, đơn chờ xử lý, cảnh báo sắp hết hàng
- Thêm / sửa / xoá sản phẩm, upload ảnh, ẩn/hiện
- Quản lý danh mục
- Quản lý đơn hàng: lọc theo trạng thái, đổi trạng thái (Chờ xác nhận → Đã xác nhận → Đang giao → Đã giao / Đã huỷ)

## Chạy thử

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

flask seed                        # tạo bảng + 12 sản phẩm mẫu
flask create-admin                # tạo tài khoản quản trị (hỏi email, tên, mật khẩu)
flask run                         # mở http://127.0.0.1:5000
```

> Email admin dùng tên miền thật dạng `admin@example.com`. Đuôi `.local`/`.test` bị
> `email-validator` từ chối nên sẽ không đăng nhập được (lệnh `create-admin` đã chặn sẵn).

Chạy test: `python -m pytest -q`

## Cấu trúc

```
shop.py                 # điểm vào (flask run)
config.py               # cấu hình: DB, phí ship, upload, ...
app/
  __init__.py           # create_app(), khởi tạo extension, đăng ký blueprint
  models.py             # User, Category, Product, Order, OrderItem
  utils.py              # giỏ hàng, bộ lọc tiền VND, admin_required, upload ảnh
  cli.py                # flask seed / flask create-admin
  main/                 # trang chủ + chi tiết sản phẩm
  auth/                 # đăng ký, đăng nhập
  cart/                 # giỏ hàng
  orders/               # thanh toán, lịch sử đơn
  admin/                # khu vực quản trị
  templates/  static/
tests/                  # pytest (28 test)
```

## Các quyết định thiết kế đáng biết

- **Giá lưu số nguyên VND**, không dùng float → không sai số làm tròn.
- **OrderItem lưu tên + giá tại thời điểm mua**, nên đổi giá/tên sản phẩm sau này không làm sai đơn cũ.
- **Trừ kho nguyên tử** (`UPDATE ... WHERE stock >= n`): hai người đặt món cuối cùng cùng lúc thì chỉ một người thành công, không bán lố.
- Sản phẩm **đã có người mua thì không xoá cứng**, chỉ ẩn đi để giữ lịch sử đơn.
- Mọi form POST (kể cả nút thêm giỏ, đăng xuất) đều có **CSRF token**; `next=` khi đăng nhập được kiểm tra chống open-redirect; mật khẩu băm bằng Werkzeug.
- Toàn bộ `/admin` được chặn bằng `before_request` (chưa đăng nhập → trang login, không phải admin → 403).

## Triển khai thật / mở rộng

- Đặt biến môi trường `SECRET_KEY` (và `DATABASE_URL` nếu dùng PostgreSQL – cần cài thêm `psycopg2-binary`), chạy bằng `gunicorn shop:app`, tắt `FLASK_DEBUG`.
- Dùng migration thay cho `create_all`: `flask db init && flask db migrate -m "init" && flask db upgrade`.
- Tìm kiếm không phân biệt hoa/thường của SQLite chỉ đúng với chữ ASCII (gõ "áo" khác "Áo"); dùng PostgreSQL (`ilike`) sẽ xử lý được tiếng Việt có dấu.
- Chưa có: thanh toán online, mã giảm giá, quên mật khẩu qua email, đánh giá sản phẩm, nhiều ảnh/sản phẩm — các điểm nối tự nhiên để làm tiếp.
