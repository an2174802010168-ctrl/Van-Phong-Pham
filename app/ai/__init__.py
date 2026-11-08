"""Blueprint 'ai': trợ lý mua sắm (RAG), tìm kiếm ngữ nghĩa, sản phẩm tương tự, tóm tắt.

Tích hợp chỉ cần MỘT dòng trong create_app() (app/__init__.py):

    from app.ai import init_app as init_ai
    init_ai(app)          # đặt SAU db.init_app(app) và các blueprint khác

init_app() tự điền các khóa cấu hình AI còn thiếu (đọc từ biến môi trường / .env)
nên KHÔNG phải sửa config.py. Khóa nào đã có trong app.config (vd. đặt trong
TestConfig) thì được giữ nguyên.
"""
import os
from flask import Blueprint

bp = Blueprint('ai', __name__)

AI_DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs')


def _flag(raw) -> bool:
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')


# khóa: (giá trị mặc định, hàm ép kiểu)
DEFAULTS = {
    # LLM: 'ollama' (cục bộ) | 'openai' (OpenAI, Gemini, Groq, LM Studio...)
    #      | 'demo' (không cần LLM: trả lời trích xuất, để chạy thử/viết test)
    'LLM_PROVIDER': ('demo', str),
    'LLM_MODEL': ('qwen2.5:3b', str),
    'LLM_BASE_URL': ('http://localhost:11434', str),
    'LLM_API_KEY': (None, str),
    'LLM_TEMPERATURE': (0.2, float),
    'LLM_TIMEOUT': (120.0, float),
    # Embedding: 'ollama' | 'openai' | 'local' (WordLlama, offline)
    'EMBED_PROVIDER': ('local', str),
    'EMBED_MODEL': ('nomic-embed-text', str),
    'EMBED_BASE_URL': (None, str),      # mặc định = LLM_BASE_URL
    'EMBED_API_KEY': (None, str),       # mặc định = LLM_API_KEY
    # Truy hồi
    'AI_TOP_K': (4, int),
    'AI_MIN_SCORE': (0.15, float),
    'AI_HYBRID_ALPHA': (0.5, float),
    'AI_MAX_CONTEXT_CHARS': (3000, int),
    'AI_MAX_QUESTION_CHARS': (500, int),
    'AI_RATE_LIMIT': (10, int),         # lượt/phút cho mỗi user (hoặc IP)
    'AI_DOCS_DIR': (AI_DOCS_DIR, str),
    # Vận hành
    'AI_REQUIRE_LOGIN': (False, _flag),  # True: chỉ người đã đăng nhập dùng AI
    'AI_AUTO_SYNC': (True, _flag),       # tự đồng bộ vector khi sản phẩm đổi
    'AI_SYNC_TTL': (60.0, float),        # giây giữa hai lần kiểm tra đồng bộ
    # Link tới trang chi tiết sản phẩm (mặc định: API JSON api.product).
    # Đặt endpoint thật của shop, vd AI_PRODUCT_ENDPOINT=shop.product_detail
    'AI_PRODUCT_ENDPOINT': ('api.product', str),
    'AI_PRODUCT_ARG': ('id', str),       # tên tham số id của endpoint đó
}


def init_app(app) -> None:
    cfg = app.config
    for key, (default, cast) in DEFAULTS.items():
        if key in cfg:
            continue
        raw = os.environ.get(key)
        cfg[key] = cast(raw) if raw not in (None, '') else default
    cfg['EMBED_BASE_URL'] = cfg['EMBED_BASE_URL'] or cfg['LLM_BASE_URL']
    cfg['EMBED_API_KEY'] = cfg['EMBED_API_KEY'] or cfg['LLM_API_KEY']
    from app.ai import models, routes, cli  # noqa: F401  (đăng ký model, route, lệnh CLI)
    app.register_blueprint(bp, url_prefix='/ai')
