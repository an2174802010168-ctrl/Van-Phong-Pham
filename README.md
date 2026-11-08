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

**AI mua sắm (`/ai`)**
- Chat với trợ lý mua sắm bằng tiếng Việt; câu trả lời có trích dẫn tới sản phẩm hoặc tài liệu liên quan, hỗ trợ hiển thị từng phần (SSE). Widget chat nổi có trên các trang.
- Tìm sản phẩm bằng từ khóa, ngữ nghĩa hoặc kết hợp; có thể nhập nhu cầu tự nhiên và khoảng giá.
- API AI cung cấp hỏi đáp, tìm kiếm, sản phẩm tương tự và tóm tắt sản phẩm; có giới hạn lượt gọi.
- Lệnh `flask ai` để index tài liệu/sản phẩm, xem thống kê, hỏi trợ lý hoặc tạo nháp mô tả sản phẩm.
- Mặc định chạy ở chế độ demo, không cần dịch vụ LLM. Trợ lý chỉ dựa trên catalog và tài liệu, không xem đơn hàng/tài khoản và không thay thế truy vấn thống kê.

## Chạy thử

Các lệnh sau chạy từ thư mục gốc của repository.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

```bash
flask seed                        # tạo bảng + 12 sản phẩm mẫu
flask create-admin                # tạo tài khoản quản trị (hỏi email, tên, mật khẩu)
flask run                         # mở http://127.0.0.1:5000
```

> Email admin dùng tên miền thật dạng `admin@example.com`. Đuôi `.local`/`.test` bị
> `email-validator` từ chối nên sẽ không đăng nhập được (lệnh `create-admin` đã chặn sẵn).

`flask seed` tạo các bảng cần thiết cho cài đặt mới. Với cơ sở dữ liệu hiện có trước khi thêm AI, chạy `flask db upgrade` để áp dụng migration tạo bảng vector `ai_chunk`.

Chạy kiểm thử cửa hàng: `python -m pytest -q`. Sau khi cài thư viện AI bên dưới, chạy thêm kiểm thử AI bằng `python -m pytest -q tests_ai.py`.

## Cấu hình và vận hành AI

- Để bật và kiểm thử các chức năng AI, cài thư viện bổ sung: `pip install -r requirements-ai.txt`. WordLlama dùng embedding cục bộ mặc định.
- Để dùng LLM thật, đặt biến môi trường trước khi khởi chạy ứng dụng: `LLM_PROVIDER=ollama` hoặc `LLM_PROVIDER=openai`, cùng model, URL và API key tương ứng. Chế độ mặc định `LLM_PROVIDER=demo` không gọi LLM; câu trả lời chỉ trích xuất thông tin liên quan.
- Khi có yêu cầu AI, hệ thống tự đồng bộ vector sản phẩm và tài liệu. Có thể chạy thủ công:

  ```bash
  flask ai index-docs
  flask ai index-products
  flask ai stats
  ```

- Tài liệu nguồn cho trợ lý nằm trong `app/ai/docs/`. Chỉ thêm chính sách cửa hàng đã được xác nhận; nếu không có thông tin trong tài liệu/catalog, trợ lý sẽ không tự suy đoán.
- Đổi embedding model thì cần tạo lại vector: `flask ai index-products --rebuild` và `flask ai index-docs --force`.
- Có thể đặt `AI_REQUIRE_LOGIN=1` để yêu cầu đăng nhập và `AI_RATE_LIMIT` để điều chỉnh số lượt AI mỗi phút. Khi dùng LLM bên ngoài, nội dung câu hỏi và ngữ cảnh được gửi tới nhà cung cấp đó; không nhập thông tin nhạy cảm.

Các endpoint AI và hướng dẫn người dùng được mô tả thêm trong `app/ai/docs/`.

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
  ai/                   # trợ lý RAG, tìm kiếm, embedding, API và lệnh CLI
    docs/               # tài liệu nguồn cho trợ lý
  templates/  static/
tests/                  # pytest cho cửa hàng
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
