# Trợ lý mua sắm

## Trợ lý làm được gì?
Mở mục Trợ lý mua sắm để đặt câu hỏi bằng tiếng Việt về sản phẩm của cửa hàng, cách đặt hàng và thanh toán.
Trợ lý tìm các sản phẩm và tài liệu liên quan rồi trả lời dựa trên đúng các thông tin đó.
Mỗi ý trong câu trả lời có số nguồn như [1], [2]; bấm vào số hoặc danh sách Nguồn để mở sản phẩm hay tài liệu gốc.
Nếu không tìm thấy thông tin, trợ lý trả lời "Xin lỗi, tôi không tìm thấy thông tin này trong tài liệu." thay vì đoán.

## Giới hạn của trợ lý
Trợ lý không thể xem đơn hàng hay tài khoản của bạn, không đặt hàng hộ và không tự đưa ra khuyến mãi.
Trợ lý chỉ trả lời được những gì có trong dữ liệu sản phẩm và tài liệu hướng dẫn của cửa hàng.
Trợ lý nhớ 3 câu hỏi gần nhất trong phiên làm việc; bấm Xóa lịch sử để bắt đầu lại.

## Lượt dùng và an toàn
Mỗi người dùng (hoặc mỗi địa chỉ IP với khách chưa đăng nhập) chỉ được gọi chức năng AI một số lần mỗi phút (AI_RATE_LIMIT, mặc định 10). Câu hỏi dài quá 500 ký tự bị cắt bớt.
Câu hỏi cố ra lệnh cho trợ lý đổi quy tắc (prompt injection) sẽ bị chặn. Mô tả sản phẩm chứa mệnh lệnh đáng ngờ như vậy cũng bị loại khỏi ngữ cảnh.
Không nhập mật khẩu hay thông tin cá nhân nhạy cảm vào trợ lý: khi dùng dịch vụ LLM trên mạng, câu hỏi và ngữ cảnh được gửi tới nhà cung cấp đó.

## Chế độ demo
Khi máy chủ chạy với LLM_PROVIDER=demo, nhãn Chế độ demo hiện trên trang. Lúc đó không có LLM: câu trả lời chỉ liệt kê sản phẩm hoặc trích nguyên văn các câu liên quan nhất. Khi cấu hình Ollama hoặc Gemini, câu trả lời là văn bản do LLM viết.
