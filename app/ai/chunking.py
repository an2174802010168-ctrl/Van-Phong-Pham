"""Chia văn bản thành các đoạn (chunk) để embedding.

Chiến lược: tách theo tiêu đề markdown -> gộp các đoạn văn tới ~size ký tự
-> đoạn quá dài thì cắt bằng cửa sổ trượt có chồng lấp (overlap).
"""
import re
from dataclasses import dataclass


@dataclass
class Chunk:
    title: str  # tiêu đề mục chứa đoạn (giúp trích dẫn và truy hồi)
    text: str


def split_sections(markdown: str) -> list[tuple[str, str]]:
    """Tách markdown theo dòng tiêu đề (#, ##, ###...) -> [(tiêu đề, nội dung)]."""
    sections: list[tuple[str, str]] = []
    title, lines = '', []
    for line in markdown.splitlines():
        m = re.match(r'^#{1,6}\s+(.*)', line)
        if m:
            if '\n'.join(lines).strip():
                sections.append((title, '\n'.join(lines).strip()))
            title, lines = m.group(1).strip(), []
        else:
            lines.append(line)
    if '\n'.join(lines).strip():
        sections.append((title, '\n'.join(lines).strip()))
    return sections


def sliding_window(text: str, size: int = 500, overlap: int = 80) -> list[str]:
    """Cắt chuỗi dài thành các cửa sổ ~size ký tự, chồng lấp overlap ký tự.
    Ưu tiên cắt ở cuối câu, sau đó ở khoảng trắng để không làm gãy từ."""
    pieces, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = max(text.rfind('. ', start + size // 2, end),
                      text.rfind('\n', start + size // 2, end))
            if cut > 0:
                end = cut + 1
            else:
                space = text.rfind(' ', start + size // 2, end)
                end = space if space > 0 else end
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in pieces if p]


def chunk_text(text: str, title: str = '', size: int = 500,
               overlap: int = 80) -> list[Chunk]:
    """Gộp các đoạn văn (cách nhau bởi dòng trống) thành chunk <= size."""
    chunks, buf = [], ''
    for para in re.split(r'\n\s*\n', text):
        para = para.strip()
        if len(para) > size:  # đoạn văn quá dài -> cửa sổ trượt
            if buf:
                chunks.append(Chunk(title, buf))
                buf = ''
            chunks += [Chunk(title, p) for p in
                       sliding_window(para, size, overlap)]
        elif len(buf) + len(para) + 2 <= size:
            buf = f'{buf}\n\n{para}' if buf else para
        else:
            chunks.append(Chunk(title, buf))
            buf = para
    if buf:
        chunks.append(Chunk(title, buf))
    return chunks


def chunk_markdown(markdown: str, size: int = 500,
                   overlap: int = 80) -> list[Chunk]:
    """Chia một tài liệu markdown thành các Chunk (theo mục, rồi theo độ dài)."""
    chunks: list[Chunk] = []
    for title, body in split_sections(markdown):
        chunks += chunk_text(body, title, size, overlap)
    return chunks
