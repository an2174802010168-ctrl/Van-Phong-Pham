"""Lớp bảo vệ đơn giản cho các chức năng AI.

1. clean_input: bỏ ký tự điều khiển, gộp khoảng trắng, giới hạn độ dài.
2. looks_like_injection: nhận diện câu kiểu "bỏ qua mọi chỉ dẫn trước đó".
   Dùng cho câu hỏi người dùng VÀ cho các đoạn ngữ cảnh truy hồi được
   (mô tả sản phẩm do người khác nhập có thể cài chỉ dẫn độc hại - indirect injection).
3. RateLimiter: giới hạn số lượt gọi AI mỗi phút cho mỗi user/IP (trong bộ nhớ,
   từng tiến trình; chạy nhiều worker -> dùng Redis nếu cần chặt hơn).
Đây là lớp phòng thủ "vừa đủ"; không thay thế được kiểm duyệt thực sự.
"""
import re
import time
from collections import defaultdict, deque
from collections.abc import Callable
from flask import current_app, request

INJECTION_PATTERNS = [
    r'ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above)\s+'
    r'(instructions?|prompts?|rules?)',
    r'disregard\s+.{0,30}(instructions?|rules?)',
    r'(system|developer)\s+prompt',
    r'you\s+are\s+now\b',
    r'bỏ\s+qua\s+(mọi|tất\s+cả|các|những)?\s*(hướng\s+dẫn|chỉ\s+dẫn|'
    r'yêu\s+cầu|quy\s+tắc|lệnh)',
    r'quên\s+(đi\s+)?(mọi|tất\s+cả|các)\s+(hướng\s+dẫn|chỉ\s+dẫn|quy\s+tắc)',
    r'(tiết\s+lộ|in\s+ra|hiển\s+thị|cho\s+xem)\s+.{0,30}'
    r'(prompt|lời\s+nhắc|chỉ\s+dẫn\s+hệ\s+thống)',
    r'<\|?(system|im_start|im_end)\|?>',
]
_INJECTION_RE = re.compile('|'.join(INJECTION_PATTERNS), re.IGNORECASE)


def clean_input(text: str, max_chars: int | None = None) -> str:
    """Làm sạch chuỗi người dùng nhập trước khi đưa vào prompt."""
    max_chars = max_chars or current_app.config['AI_MAX_QUESTION_CHARS']
    text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', ' ', text or '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_chars]


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION_RE.search(text or ''))


def filter_contexts(items: list, text: Callable = lambda c: c.text
                    ) -> tuple[list, list]:
    """Tách các đoạn ngữ cảnh an toàn / đáng ngờ (chứa chỉ dẫn lạ)."""
    safe, blocked = [], []
    for item in items:
        (blocked if looks_like_injection(text(item)) else safe).append(item)
    return safe, blocked


class RateLimiter:
    """Cửa sổ trượt 60 giây: tối đa `limit` lượt cho mỗi khóa."""

    def __init__(self, window: float = 60.0):
        self.window = window
        self.calls: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        q = self.calls[key]
        while q and now - q[0] > self.window:
            q.popleft()  # bỏ các lượt đã quá 60 giây
        if len(q) >= limit:
            return False
        q.append(now)
        return True


rate_limiter = RateLimiter()  # dùng chung trong một tiến trình


def rate_key() -> str:
    """Người đã đăng nhập -> theo user id ; khách -> theo địa chỉ IP."""
    try:
        from flask_login import current_user
        if current_user.is_authenticated:
            return f'user:{current_user.get_id()}'
    except Exception:  # không dùng Flask-Login / không có request context
        pass
    return f'ip:{request.remote_addr}'


def check_rate() -> bool:
    return rate_limiter.allow(rate_key(), current_app.config['AI_RATE_LIMIT'])
