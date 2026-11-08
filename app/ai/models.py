import sqlalchemy as sa
import sqlalchemy.orm as so
from datetime import datetime, timezone
from typing import Optional
from app import db


class AiChunk(db.Model):
    """Một đoạn văn bản đã được embedding – dùng cho RAG.

    source: 'product' (sản phẩm) hoặc 'doc' (tài liệu hướng dẫn trong app/ai/docs)
    ref_id: id sản phẩm hoặc tên tệp tài liệu
    embedding: vector float32 lưu dạng bytes (BLOB)
    model: tên model embedding đã tạo vector (đổi model phải index lại)
    content_hash: băm nội dung lúc index -> biết sản phẩm nào đã đổi, cần embed lại
    """
    __tablename__ = 'ai_chunk'
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    source: so.Mapped[str] = so.mapped_column(sa.String(10), index=True)
    ref_id: so.Mapped[str] = so.mapped_column(sa.String(120), index=True)
    chunk_index: so.Mapped[int] = so.mapped_column(default=0)
    title: so.Mapped[Optional[str]] = so.mapped_column(sa.String(200))
    text: so.Mapped[str] = so.mapped_column(sa.Text)
    embedding: so.Mapped[bytes] = so.mapped_column(sa.LargeBinary)
    model: so.Mapped[str] = so.mapped_column(sa.String(100), index=True)
    content_hash: so.Mapped[Optional[str]] = so.mapped_column(sa.String(40))
    created: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<AiChunk {self.source}:{self.ref_id}#{self.chunk_index}>'
