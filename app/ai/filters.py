"""Bộ lọc giá từ câu hỏi tự nhiên: "áo dưới 300k", "laptop từ 10 triệu đến 20 triệu".

Embedding không hiểu CON SỐ (300k hay 3 triệu đều "gần" nhau), nên phần điều kiện
về giá được tách ra và lọc bằng SQL thật. Chỉ nhận khi có từ khóa so sánh VÀ đơn vị
tiền ("k", "nghìn", "triệu", "đ"...) để không nhầm "iPhone 15" hay "5G" thành giá.
"""
import re
from dataclasses import dataclass

UNITS = {'triệu': 1_000_000, 'tr': 1_000_000, 'nghìn': 1_000, 'ngàn': 1_000,
         'k': 1_000, 'đồng': 1, 'đ': 1, 'vnđ': 1, 'vnd': 1}
MAX_WORDS = ('dưới', 'không quá', 'tối đa', 'ít hơn', 'đến', 'tới', 'nhỏ hơn')
MIN_WORDS = ('trên', 'từ', 'ít nhất', 'hơn', 'lớn hơn')

_UNIT_RE = '|'.join(sorted(UNITS, key=len, reverse=True))
_KW_RE = '|'.join(sorted(MAX_WORDS + MIN_WORDS, key=len, reverse=True))
# [từ khóa so sánh] SỐ ĐƠN-VỊ [trở lên|trở xuống]   – phải có từ khóa HOẶC "trở lên/xuống"
_PRICE_RE = re.compile(
    rf'(?:(?P<kw>{_KW_RE})\s*)?(?P<num>\d+(?:[.,]\d+)*)\s*(?P<unit>{_UNIT_RE})\b'
    r'(?:\s+trở\s+(?P<dir>lên|xuống))?', re.IGNORECASE)


@dataclass
class PriceRange:
    min: float | None = None
    max: float | None = None

    def __bool__(self) -> bool:
        return self.min is not None or self.max is not None

    def apply(self, stmt, column):
        """Thêm điều kiện giá (gồm cả hai đầu mút) vào câu SELECT."""
        if self.min is not None:
            stmt = stmt.where(column >= self.min)
        if self.max is not None:
            stmt = stmt.where(column <= self.max)
        return stmt

    def describe(self) -> str:
        parts = []
        if self.min is not None:
            parts.append(f'từ {self.min:,.0f}đ'.replace(',', '.'))
        if self.max is not None:
            parts.append(f'đến {self.max:,.0f}đ'.replace(',', '.'))
        return ' '.join(parts)


def _number(text: str) -> float:
    """'1.500.000' -> 1500000 (dấu chấm ngăn nghìn) ; '1,5' / '1.5' -> 1.5."""
    if re.fullmatch(r'\d{1,3}([.,]\d{3})+', text):
        return float(re.sub(r'[.,]', '', text))
    return float(text.replace(',', '.'))


def parse_price(query: str) -> PriceRange:
    """Rút khoảng giá (VND) từ câu hỏi; không có -> PriceRange rỗng."""
    result = PriceRange()
    for m in _PRICE_RE.finditer(query or ''):
        kw, direction = m.group('kw'), m.group('dir')
        if not kw and not direction:
            continue  # chỉ có "500k" trơ trọi: không biết là tối đa hay tối thiểu
        value = _number(m.group('num')) * UNITS[m.group('unit').lower()]
        is_max = direction.lower() == 'xuống' if direction \
            else kw.lower() in MAX_WORDS
        if is_max:
            result.max = value if result.max is None else min(result.max, value)
        else:
            result.min = value if result.min is None else max(result.min, value)
    return result


def remove_price(query: str) -> str:
    """Bỏ cụm điều kiện giá khỏi câu hỏi trước khi embedding/chấm từ khóa
    (để "áo dưới 300k" tìm theo "áo"). Bỏ xong mà rỗng -> giữ câu gốc."""
    def drop(m):  # chỉ bỏ cụm mà parse_price thật sự hiểu là điều kiện giá
        return ' ' if (m.group('kw') or m.group('dir')) else m.group(0)
    stripped = re.sub(r'\s+', ' ', _PRICE_RE.sub(drop, query or '')).strip()
    return stripped or (query or '')
