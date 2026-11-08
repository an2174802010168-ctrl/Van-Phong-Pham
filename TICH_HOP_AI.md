# Thêm LLM + RAG vào FlaskShop

Module `app/ai/` **tự đủ**: không sửa `models.py`, `config.py`, `base.html`; chỉ thêm **1 dòng** vào `create_app()`.

## Chức năng
| URL | Làm gì |
|---|---|
| `/ai/assistant?q=...` | Trợ lý mua sắm (RAG): hỏi về sản phẩm, đặt hàng, thanh toán; trả lời có trích dẫn [1] [2], hỗ trợ stream SSE |
| `/ai/search?q=...&mode=` | Tìm sản phẩm theo ngữ nghĩa / từ khóa / lai, hiểu cả điều kiện giá ("áo dưới 300k", "laptop từ 10 triệu trở lên") |
| `/ai/api/ask`, `/ai/api/search` | Bản JSON của hai chức năng trên |
| `/ai/api/products/<id>/similar` | Sản phẩm tương tự (nhúng bằng `{% include 'ai/_similar.html' %}`) |
| `/ai/api/products/<id>/summary` | Tóm tắt sản phẩm một câu |
| `flask ai describe "Tên" --features "..."` | Viết nháp mô tả sản phẩm cho chủ shop |

Giá và tình trạng còn hàng trong câu trả lời luôn đọc lại từ CSDL lúc trả lời (không lấy từ vector cũ). Sản phẩm ngừng bán không bao giờ được gợi ý.

## Cài đặt (5 bước)

**1. Chép file** — giải nén zip này vào thư mục gốc project (không ghi đè file nào của bạn):
`app/ai/`, `app/templates/ai/`, `tools/`, `tests_ai.py`, `requirements-ai.txt`, `.env.*`

**2. Cài thư viện:** `pip install -r requirements-ai.txt`

**3. Thêm 1 dòng vào `create_app()` trong `app/__init__.py`** (sau `db.init_app(app)` và các blueprint khác):
```python
    from app.ai import init_app as init_ai
    init_ai(app)
```

**4. Tạo bảng `ai_chunk`:** `flask db migrate -m "ai chunks"` rồi `flask db upgrade` (hoặc `db.create_all()` nếu bạn không dùng migration).

**5. Chạy:** mặc định là **chế độ demo** (không cần LLM, không cần mạng) nên chạy được ngay. Lần đầu có người dùng AI, hệ thống tự index tài liệu + sản phẩm (hoặc chạy tay `flask ai index-docs && flask ai index-products`).

Thêm link vào navbar: `url_for('ai.assistant')` và `url_for('ai.search')`.

## Dùng LLM thật
Chép một trong ba tệp mẫu thành `.env` (nhớ `.env` phải được nạp trước khi gọi `create_app`):
- `.env.ollama` — chạy cục bộ, miễn phí (khuyên dùng): `ollama pull qwen2.5:3b` và `ollama pull bge-m3`
- `.env.gemini` — Gemini/OpenAI/Groq qua API tương thích OpenAI (cần khóa API; kiểm tra lại tên model theo tài liệu nhà cung cấp)
- `.env.demo` — offline

**Đổi model embedding thì phải index lại:** `flask ai index-products --rebuild && flask ai index-docs --force`.

## Chỉnh theo shop của bạn
- **Tài liệu RAG** nằm ở `app/ai/docs/*.md`. Các tệp mẫu chỉ ghi những điều suy ra từ code hiện có (COD, email xác nhận, API). **Hãy thêm chính sách thật** (đổi trả, bảo hành, thời gian giao hàng, khuyến mãi) thành tệp `.md` mới: chưa có tệp thì trợ lý trả lời "không tìm thấy" thay vì bịa. Sửa xong hệ thống tự index lại (hoặc `flask ai index-docs`).
- **Link sản phẩm:** mặc định trỏ tới `api.product` (JSON). Đặt `AI_PRODUCT_ENDPOINT=<endpoint trang chi tiết thật>` (và `AI_PRODUCT_ARG` nếu tham số không tên `id`).
- **Chỉ cho người đăng nhập dùng:** `AI_REQUIRE_LOGIN=1` (cần Flask-Login).
- **Chặn chi phí:** `AI_RATE_LIMIT` (lượt/phút/user hoặc IP). Giới hạn đếm trong bộ nhớ từng tiến trình; nhiều worker thì mỗi worker đếm riêng. Sau reverse proxy cần `ProxyFix` để `request.remote_addr` là IP khách.
- Các khóa khác: xem `DEFAULTS` trong `app/ai/__init__.py`.

## Kiểm thử
`python tests_ai.py` hoặc `python -m pytest tests_ai.py -v` (offline, 54 test). Nếu `Product`/`Category`/`User` của bạn có thêm trường bắt buộc, sửa hàm `make_products()` ở đầu tệp.

## Giới hạn cần biết
- **Embedding mặc định (`local`, WordLlama) học chủ yếu từ tiếng Anh**: với tiếng Việt, cosine của mọi cặp câu đều ~0,55–0,67 nên gần như không phân biệt được liên quan hay không. Nó đủ để chạy thử; hệ thống vẫn đúng nhờ phần từ khóa của tìm kiếm lai. Khi chạy thật hãy dùng `bge-m3` (Ollama) hoặc embedding của Gemini/OpenAI, rồi chỉnh `AI_MIN_SCORE` / `AI_HYBRID_ALPHA` theo dữ liệu của bạn (các giá trị trong `.env.ollama`/`.env.gemini` chỉ là điểm khởi đầu, chưa kiểm chứng).
- Kho vector là bảng SQL + NumPy: đủ cho vài chục nghìn sản phẩm; lớn hơn nên chuyển sang pgvector/Chroma.
- Trợ lý chỉ trả lời từ catalog + tài liệu; **không xem được đơn hàng/tài khoản của khách** và không tổng hợp kiểu "rẻ nhất", "bán chạy nhất" (đó là truy vấn SQL, không phải truy hồi).
