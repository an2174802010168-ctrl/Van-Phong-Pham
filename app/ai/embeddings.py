"""Embedding: biến văn bản thành vector số để so sánh độ tương đồng (cosine).

Ba nhà cung cấp (EMBED_PROVIDER):
  ollama -> POST {base}/api/embed           {"model", "input": [...]}
  openai -> POST {base}/embeddings          {"model", "input": [...]}
  local  -> WordLlama (trọng số đi kèm gói PyPI, chạy offline, 256 chiều)
Mọi vector trả về đã chuẩn hóa L2 => cosine = tích vô hướng.
"""
import os
import numpy as np
import requests
from flask import current_app


class EmbeddingError(RuntimeError):
    """Lỗi khi gọi dịch vụ embedding (thông báo rõ cho người dùng)."""


def normalize(matrix: np.ndarray) -> np.ndarray:
    """Chuẩn hóa từng hàng về độ dài 1 (L2)."""
    matrix = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


_wordllama = None  # nạp một lần, dùng lại (mất ~0,1 s)


def _load_wordllama():
    global _wordllama
    if _wordllama is None:
        import wordllama
        from wordllama import WordLlama
        _wordllama = WordLlama.load(
            cache_dir=os.path.dirname(wordllama.__file__),
            disable_download=True)  # không tải gì từ Internet
    return _wordllama


class Embedder:
    def __init__(self, provider: str, model: str, base_url: str = '',
                 api_key: str | None = None, timeout: float = 60):
        self.provider = provider
        self.model = model
        self.base_url = (base_url or '').rstrip('/')
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_config(cls) -> 'Embedder':
        cfg = current_app.config
        return cls(cfg['EMBED_PROVIDER'], cfg['EMBED_MODEL'],
                   cfg['EMBED_BASE_URL'], cfg['EMBED_API_KEY'],
                   cfg['LLM_TIMEOUT'])

    @property
    def name(self) -> str:
        """Tên lưu kèm vector trong CSDL, vd 'ollama:bge-m3'."""
        if self.provider == 'local':
            return 'local:wordllama-l2-256'
        return f'{self.provider}:{self.model}'

    def embed(self, texts: list[str]) -> np.ndarray:
        """Trả về ma trận (len(texts), số chiều), mỗi hàng đã chuẩn hóa L2."""
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        if self.provider == 'local':
            vectors = _load_wordllama().embed(texts)
        elif self.provider == 'ollama':
            vectors = self._embed_ollama(texts)
        elif self.provider == 'openai':
            vectors = self._embed_openai(texts)
        else:
            raise EmbeddingError(f'EMBED_PROVIDER không hợp lệ: {self.provider}')
        return normalize(vectors)

    def _post(self, url: str, payload: dict, headers: dict | None = None):
        try:
            r = requests.post(url, json=payload, headers=headers,
                              timeout=self.timeout)
        except requests.RequestException as e:
            raise EmbeddingError(f'Không kết nối được {url}: {e}') from e
        if r.status_code != 200:
            raise EmbeddingError(f'{url} trả lỗi {r.status_code}: '
                                 f'{r.text[:200]}')
        return r.json()

    def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        data = self._post(f'{self.base_url}/api/embed',
                          {'model': self.model, 'input': texts})
        return data['embeddings']

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key or not self.api_key.strip():
            raise EmbeddingError(
                'EMBED_API_KEY chưa được cấu hình cho provider openai.')
        headers = {'Authorization': f'Bearer {self.api_key}'}
        data = self._post(f'{self.base_url}/embeddings',
                          {'model': self.model, 'input': texts}, headers)
        items = sorted(data['data'], key=lambda d: d['index'])
        return [item['embedding'] for item in items]
