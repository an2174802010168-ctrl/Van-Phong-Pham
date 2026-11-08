"""Kho vector tối giản: SQLite/Postgres (bảng ai_chunk) + NumPy.

Vector float32 lưu dạng BLOB. Khi tìm kiếm: nạp các vector cùng model, xếp thành
ma trận rồi tính cosine bằng một phép nhân ma trận. Đủ nhanh cho vài chục nghìn
đoạn (cửa hàng nhỏ/vừa); lớn hơn -> pgvector, sqlite-vec, Chroma...

`keep` là hàm lọc (AiChunk -> bool) chạy TRƯỚC khi tính điểm, dùng để loại sản phẩm
ngừng bán / ngoài khoảng giá.
"""
from collections.abc import Callable
from dataclasses import dataclass
import numpy as np
import sqlalchemy as sa
from app import db
from app.ai.models import AiChunk
from app.ai.chunking import Chunk
from app.ai.keywords import keyword_scores

Keep = Callable[[AiChunk], bool] | None


def to_blob(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


@dataclass
class Hit:
    chunk: AiChunk
    score: float          # điểm cuối cùng dùng để xếp hạng
    semantic: float = 0.0  # cosine giữa vector câu hỏi và vector đoạn
    keyword: float = 0.0   # điểm khớp từ khóa


class VectorStore:
    def __init__(self, model_name: str):
        self.model = model_name  # chỉ so sánh vector của cùng một model

    def upsert(self, source: str, ref_id: str, chunks: list[Chunk],
               vectors: np.ndarray, content_hash: str | None = None) -> int:
        """Xóa các đoạn cũ của (source, ref_id) rồi ghi các đoạn mới."""
        self.delete(source, ref_id)
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            db.session.add(AiChunk(
                source=source, ref_id=str(ref_id), chunk_index=i,
                title=chunk.title[:200], text=chunk.text,
                embedding=to_blob(vec), model=self.model,
                content_hash=content_hash))
        db.session.commit()
        return len(chunks)

    def delete(self, source: str, ref_id: str | None = None) -> int:
        """Xóa các đoạn của model này (theo nguồn, và theo ref_id nếu có)."""
        query = sa.delete(AiChunk).where(AiChunk.model == self.model,
                                         AiChunk.source == source)
        if ref_id is not None:
            query = query.where(AiChunk.ref_id == str(ref_id))
        result = db.session.execute(query)
        db.session.commit()
        return result.rowcount

    def count(self, source: str) -> int:
        return db.session.scalar(
            sa.select(sa.func.count()).select_from(AiChunk).where(
                AiChunk.model == self.model, AiChunk.source == source)) or 0

    def hashes(self, source: str) -> dict[str, str | None]:
        """{ref_id: content_hash} của các đoạn đã index (để biết cái nào đổi)."""
        rows = db.session.execute(sa.select(
            AiChunk.ref_id, AiChunk.content_hash).where(
            AiChunk.model == self.model, AiChunk.source == source))
        return {ref: h for ref, h in rows}

    def _load(self, source: str | list[str] | None, keep: Keep = None):
        """Nạp các đoạn (cùng model, lọc theo nguồn) và ma trận vector."""
        query = sa.select(AiChunk).where(AiChunk.model == self.model)
        if isinstance(source, str):
            query = query.where(AiChunk.source == source)
        elif source:
            query = query.where(AiChunk.source.in_(source))
        chunks = [c for c in db.session.scalars(query) if not keep or keep(c)]
        if not chunks:
            return [], np.zeros((0, 0), dtype=np.float32)
        return chunks, np.vstack([from_blob(c.embedding) for c in chunks])

    def search(self, qvec: np.ndarray, k: int = 4, source=None,
               min_score: float = 0.0, keep: Keep = None
               ) -> list[tuple[AiChunk, float]]:
        """Top-k đoạn có cosine lớn nhất với vector câu hỏi."""
        chunks, matrix = self._load(source, keep)
        if not chunks:
            return []
        scores = matrix @ qvec  # vector đã chuẩn hóa => cosine
        order = np.argsort(-scores)[:k]
        return [(chunks[i], float(scores[i])) for i in order
                if scores[i] >= min_score]

    def hybrid_search(self, query: str, qvec: np.ndarray, k: int = 4,
                      source=None, alpha: float = 0.5, min_score: float = 0.0,
                      keep: Keep = None) -> list[Hit]:
        """Tìm kiếm lai: score = alpha*cosine + (1-alpha)*điểm từ khóa.
        alpha=1 -> thuần ngữ nghĩa ; alpha=0 -> thuần từ khóa."""
        chunks, matrix = self._load(source, keep)
        if not chunks:
            return []
        semantic = np.clip(matrix @ qvec, 0, 1)
        keyword = np.array(keyword_scores(
            query, [f'{c.title or ""} {c.text}' for c in chunks]))
        scores = alpha * semantic + (1 - alpha) * keyword
        order = np.argsort(-scores)[:k]
        return [Hit(chunks[i], float(scores[i]), float(semantic[i]),
                    float(keyword[i])) for i in order
                if scores[i] >= min_score]

    def neighbors(self, source: str, ref_id: str, k: int = 4,
                  keep: Keep = None) -> list[tuple[AiChunk, float]]:
        """Các đoạn gần nhất với một đoạn đã lưu (sản phẩm tương tự), bỏ chính nó."""
        chunks, matrix = self._load(source, keep)
        me = [i for i, c in enumerate(chunks) if c.ref_id == str(ref_id)]
        if not me:
            return []
        scores = matrix @ matrix[me[0]]
        order = [i for i in np.argsort(-scores) if chunks[i].ref_id != str(ref_id)]
        return [(chunks[i], float(scores[i])) for i in order[:k]]

    def stats(self) -> list[tuple[str, str, int]]:
        """Số đoạn theo (model, source) – cho lệnh `flask ai stats`."""
        query = sa.select(AiChunk.model, AiChunk.source, sa.func.count()) \
            .group_by(AiChunk.model, AiChunk.source)
        return [tuple(row) for row in db.session.execute(query)]
