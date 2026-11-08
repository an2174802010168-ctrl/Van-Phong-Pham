# API cho lập trình viên

## API sản phẩm
GET /api/products trả về danh sách sản phẩm đang bán dạng JSON, hỗ trợ tham số q (lọc theo tên), page và per_page (tối đa 50).
GET /api/products/ID trả về chi tiết một sản phẩm, gồm id, name, description, price, stock, in_stock, category và image.
Sản phẩm ngừng bán hoặc không tồn tại trả về lỗi 404 dạng JSON.

## API trợ lý AI
GET /ai/api/ask?q=CÂU_HỎI trả lời câu hỏi, kèm danh sách nguồn trích dẫn.
GET /ai/api/search?q=TỪ_KHÓA&mode=hybrid tìm sản phẩm theo ngữ nghĩa; mode nhận hybrid, semantic hoặc keyword.
GET /ai/api/products/ID/similar trả về các sản phẩm tương tự.
GET /ai/api/products/ID/summary trả về bản tóm tắt một câu của sản phẩm.
Các API AI bị giới hạn số lượt mỗi phút; vượt giới hạn sẽ nhận mã 429.
