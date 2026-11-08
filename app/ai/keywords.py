"""Xử lý từ khóa đơn giản (lexical): tách từ, bỏ từ dừng, chấm điểm khớp từ.

Dùng cho: tìm kiếm từ khóa, phần "lai" (hybrid) của truy hồi, chế độ demo.
Tiếng Việt viết tách âm tiết nên ngoài từ đơn ta lấy thêm cặp âm tiết liền
nhau (bigram): "theo dõi", "người dùng", "tìm kiếm"...
"""
import math
import re

STOPWORDS = set('''
là và của có cho các những một được trong với để thì này đó khi làm sao thế
nào gì không bạn tôi mình ở ra vào như cũng đã sẽ đang rất hay hoặc bị từ về
theo nếu mà nhé ạ à ơi vậy thể cách hãy nên lại thêm hơn nhiều ai đâu bao
nhiêu hôm nay giờ muốn cần phải biết
the a an is are of to and or in on for with how what do does can i you my
'''.split())


def tokenize(text: str) -> list[str]:
    """Chữ thường, tách theo ký tự chữ/số (giữ dấu tiếng Việt)."""
    return re.findall(r'\w+', text.lower())


def terms(text: str) -> set[str]:
    """Tập thuật ngữ = từ đơn không phải từ dừng + bigram (trừ cặp toàn từ dừng)."""
    toks = tokenize(text)
    result = {t for t in toks if t not in STOPWORDS and len(t) > 1}
    for a, b in zip(toks, toks[1:]):
        if a not in STOPWORDS or b not in STOPWORDS:
            result.add(f'{a} {b}')
    return result


def keyword_scores(query: str, texts: list[str]) -> list[float]:
    """Điểm khớp từ khóa trong [0, 1] cho từng văn bản.

    Mỗi thuật ngữ của câu hỏi có trọng số IDF (càng hiếm càng quan trọng);
    điểm = tổng IDF các thuật ngữ khớp / tổng IDF mọi thuật ngữ câu hỏi.
    """
    q_terms = terms(query)
    if not q_terms or not texts:
        return [0.0] * len(texts)
    doc_terms = [terms(t) for t in texts]
    n = len(texts)
    idf = {t: math.log(1 + n / (1 + sum(t in d for d in doc_terms)))
           for t in q_terms}
    total = sum(idf.values())
    return [sum(idf[t] for t in q_terms & d) / total for d in doc_terms]


def product_match(question: str, fields: dict[str, str]) -> int:
    """Return matched product keywords when at least half the query is relevant."""
    words = {t for t in tokenize(question)
             if t not in STOPWORDS and len(t) > 1 and not t.isdigit()}
    searchable = set(tokenize(' '.join(
        fields.get(key, '') for key in ('Tên', 'Danh mục', 'Mô tả'))))
    matched = len(words & searchable)
    return matched if words and matched >= math.ceil(len(words) / 2) else 0


def capital_phrases(text: str) -> list[str]:
    """Cụm từ viết hoa liên tiếp, bỏ qua từ đầu câu: 'Hà Nội' -> 'HàNội'."""
    phrases, current, prev = [], '', '.'
    for tok in re.findall(r'\w+|[^\w\s]', text):
        if tok[0].isupper() and prev not in '.!?':
            current += tok
        else:
            if len(current) > 1:
                phrases.append(current)
            current = ''
        prev = tok
    return phrases + ([current] if len(current) > 1 else [])


def top_terms(text: str, n: int = 3) -> list[str]:
    """Thuật ngữ nổi bật (gợi ý hashtag ở chế độ demo), theo thứ tự ưu tiên:
    cụm viết hoa giữa câu (Hà Nội, Flask) > từ Latin dài (vector) > cặp âm tiết."""
    latin = [w for w in re.findall(r'\w+', text) if w.isascii()
             and len(w) > 3 and w.lower() not in STOPWORDS and not w.isdigit()]
    toks = tokenize(text)
    pairs = [a + b for a, b in zip(toks, toks[1:])
             if a not in STOPWORDS and b not in STOPWORDS
             and len(a) > 1 and len(b) > 1 and not a.isdigit()]
    result: list[str] = []
    for t in capital_phrases(text) + latin + pairs:
        if t.lower() not in [r.lower() for r in result]:
            result.append(t)
    return result[:n]
