"""Chế độ demo: "LLM giả" chạy offline, KHÔNG sinh văn bản mới.

Nó đọc đúng các messages mà LLM thật sẽ nhận (cùng prompt), rồi TRÍCH XUẤT thông tin
từ ngữ cảnh. Nhờ vậy cả pipeline RAG chạy được khi chưa có Ollama/khóa API, và test
không phụ thuộc mạng.
"""
import re
from app.ai import prompts
from app.ai.filters import remove_price
from app.ai.keywords import product_match, terms

DEMO_TAG = '[Chế độ demo – không dùng LLM]'


def demo_reply(messages: list[dict[str, str]]) -> str:
    """Chọn cách trả lời theo prompt hệ thống (cùng prompt như LLM thật)."""
    system, user = messages[0]['content'], messages[-1]['content']
    if system == prompts.SYSTEM_SUMMARY:
        return f'{DEMO_TAG} {summary_line(user)}'
    if system == prompts.SYSTEM_DESCRIBE:
        return f'{DEMO_TAG} (cần LLM thật để viết mô tả) {user.splitlines()[0]}'
    return rag_extract(user)


def parse_prompt(user_msg: str) -> tuple[str, list[tuple[int, str]]]:
    """Tách câu hỏi và các đoạn ngữ cảnh [n] từ prompt do rag.py tạo ra."""
    question = user_msg.rsplit('CÂU HỎI:', 1)[-1].strip()
    blocks = re.findall(r'^\[(\d+)\] [^\n]*\n(.*?)(?=^\[\d+\] |^</context>)',
                        user_msg, flags=re.S | re.M)
    return question, [(int(n), body.strip()) for n, body in blocks]


def sentences(text: str) -> list[str]:
    """Tách câu: theo dấu chấm/chấm hỏi/xuống dòng; bỏ ký hiệu markdown."""
    text = re.sub(r'[#*`>]', '', text)
    parts = re.split(r'(?<=[.!?])\s+|\n+', text)
    return [p.strip(' -•\t') for p in parts if len(p.strip(' -•\t')) > 15]


def product_fields(body: str) -> dict[str, str]:
    """Đọc các dòng 'Tên: ...', 'Giá: ...' trong ngữ cảnh sản phẩm (rag.product_text)."""
    return dict(re.findall(r'^(Tên|Danh mục|Giá|Tình trạng|Mô tả): (.*)$',
                           body, flags=re.M))


def rag_extract(user_msg: str, max_sentences: int = 3,
                min_overlap: int = 2) -> str:
    """Sản phẩm: liệt kê tên – giá – tình trạng của sản phẩm khớp câu hỏi (product_match).
    Tài liệu: lấy các câu chung nhiều thuật ngữ với câu hỏi nhất. Luôn kèm [n]."""
    question, contexts = parse_prompt(user_msg)
    q_terms = terms(question)
    products, scored = [], []
    for n, body in contexts:
        fields = product_fields(body)
        if 'Tên' in fields:  # ngữ cảnh sản phẩm
            matched = product_match(remove_price(question), fields)
            if matched:
                products.append((matched, -n, n, fields))
            continue
        for s in sentences(body):
            overlap = len(q_terms & terms(s))
            if overlap >= min_overlap:
                scored.append((overlap, -n, s, n))
    lines = []
    for _, _, n, f in sorted(products, reverse=True)[:max_sentences]:
        lines.append(f"- {f['Tên']} – {f.get('Giá', '?')} – "
                     f"{f.get('Tình trạng', '?')} [{n}]")
    for _, _, s, n in sorted(scored, reverse=True)[:max_sentences]:
        lines.append(f'- {s} [{n}]')
    if not lines:
        return f'{DEMO_TAG} {prompts.NO_ANSWER}'
    return f'{DEMO_TAG} Thông tin liên quan nhất trong ngữ cảnh:\n' + \
        '\n'.join(lines)


def summary_line(text: str, max_chars: int = 100) -> str:
    """Tóm tắt demo: ưu tiên dòng 'Mô tả:' (nếu là sản phẩm), lấy câu đầu tiên."""
    desc = product_fields(text).get('Mô tả') or text
    s = re.split(r'(?<=[.!?])\s', desc.strip(), maxsplit=1)[0]
    return s if len(s) <= max_chars else s[:max_chars].rsplit(' ', 1)[0] + '…'
