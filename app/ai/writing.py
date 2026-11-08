"""Các chức năng viết dùng LLM: tóm tắt sản phẩm, viết mô tả (cho chủ shop)."""
from app.ai import prompts
from app.ai.llm import LLMClient

_summary_cache: dict[tuple, str] = {}  # cùng sản phẩm + cùng model -> khỏi gọi lại
_CACHE_MAX = 256


def _ask(system: str, user: str, temperature: float = 0.2) -> str:
    messages = [{'role': 'system', 'content': system},
                {'role': 'user', 'content': user}]
    return LLMClient.from_config().chat(messages,
                                        temperature=temperature).strip()


def summarize_product(text: str) -> str:
    """Tóm tắt một sản phẩm (đầu vào: rag.product_text) thành một câu."""
    llm = LLMClient.from_config()
    key = (llm.provider, llm.model, text)
    if key not in _summary_cache:
        if len(_summary_cache) >= _CACHE_MAX:
            _summary_cache.clear()
        _summary_cache[key] = _ask(prompts.SYSTEM_SUMMARY, text)
    return _summary_cache[key]


def describe_product(name: str, category: str = '', features: str = '') -> str:
    """Viết nháp mô tả sản phẩm từ vài thông tin – chủ shop đọc lại rồi mới đăng."""
    lines = [f'Tên: {name}']
    if category:
        lines.append(f'Danh mục: {category}')
    if features:
        lines.append(f'Đặc điểm: {features}')
    return _ask(prompts.SYSTEM_DESCRIBE, '\n'.join(lines), temperature=0.6)
