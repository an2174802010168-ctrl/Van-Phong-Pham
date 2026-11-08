"""LLMClient: gọi mô hình ngôn ngữ qua HTTP với cùng một giao diện chat().

messages theo chuẩn chat: [{"role": "system"|"user"|"assistant", "content": "..."}]
  ollama -> POST {base}/api/chat           (stream: mỗi dòng một JSON - NDJSON)
  openai -> POST {base}/chat/completions   (stream: Server-Sent Events "data: ...")
  demo   -> không gọi mạng, trả lời trích xuất (app/ai/demo.py)
"""
import json
from collections.abc import Iterator
import requests
from flask import current_app
from app.ai.demo import demo_reply


class LLMError(RuntimeError):
    """Lỗi khi gọi LLM (mất kết nối, sai khóa API, hết hạn mức...)."""


Messages = list[dict[str, str]]


class LLMClient:
    def __init__(self, provider: str, model: str, base_url: str = '',
                 api_key: str | None = None, temperature: float = 0.2,
                 timeout: float = 120):
        self.provider = provider
        self.model = model
        self.base_url = (base_url or '').rstrip('/')
        self.api_key = api_key
        self.temperature = temperature
        self.timeout = timeout

    @classmethod
    def from_config(cls) -> 'LLMClient':
        cfg = current_app.config
        return cls(cfg['LLM_PROVIDER'], cfg['LLM_MODEL'], cfg['LLM_BASE_URL'],
                   cfg['LLM_API_KEY'], cfg['LLM_TEMPERATURE'],
                   cfg['LLM_TIMEOUT'])

    @property
    def is_demo(self) -> bool:
        return self.provider == 'demo'

    def chat(self, messages: Messages, stream: bool = False,
             temperature: float | None = None) -> str | Iterator[str]:
        """Gửi hội thoại, nhận câu trả lời.
        stream=False -> str ; stream=True -> iterator các mẩu văn bản."""
        temp = self.temperature if temperature is None else temperature
        if self.provider == 'demo':
            text = demo_reply(messages)
            return _word_stream(text) if stream else text
        if self.provider == 'ollama':
            return self._ollama(messages, stream, temp)
        if self.provider == 'openai':
            return self._openai(messages, stream, temp)
        raise LLMError(f'LLM_PROVIDER không hợp lệ: {self.provider}')

    def _post(self, url: str, payload: dict, stream: bool,
              headers: dict | None = None) -> requests.Response:
        try:
            r = requests.post(url, json=payload, headers=headers,
                              stream=stream, timeout=self.timeout)
        except requests.ConnectionError as e:
            raise LLMError(f'Không kết nối được {url}. '
                           'Dịch vụ LLM đã chạy chưa?') from e
        except requests.Timeout as e:
            raise LLMError(f'Hết thời gian chờ {self.timeout}s: {url}') from e
        if r.status_code != 200:
            raise LLMError(f'{url} trả lỗi {r.status_code}: {r.text[:300]}')
        return r

    # ---------- Ollama: /api/chat ----------
    def _ollama(self, messages: Messages, stream: bool, temp: float):
        payload = {'model': self.model, 'messages': messages,
                   'stream': stream, 'options': {'temperature': temp}}
        r = self._post(f'{self.base_url}/api/chat', payload, stream)
        if not stream:
            return r.json()['message']['content']
        return _ollama_stream(r)

    # ---------- OpenAI-compatible: /chat/completions ----------
    def _openai(self, messages: Messages, stream: bool, temp: float):
        if not self.api_key or not self.api_key.strip():
            raise LLMError('LLM_API_KEY chưa được cấu hình cho provider openai.')
        payload = {'model': self.model, 'messages': messages,
                   'temperature': temp, 'stream': stream}
        headers = {'Authorization': f'Bearer {self.api_key}'}
        r = self._post(f'{self.base_url}/chat/completions', payload, stream,
                       headers)
        if not stream:
            return r.json()['choices'][0]['message']['content']
        return _openai_stream(r)


def _ollama_stream(r: requests.Response) -> Iterator[str]:
    """NDJSON: mỗi dòng {"message": {"content": "..."}, "done": false}."""
    for line in r.iter_lines():  # bytes; json.loads tự giải mã UTF-8
        if not line:
            continue
        data = json.loads(line)
        if data.get('message', {}).get('content'):
            yield data['message']['content']
        if data.get('done'):
            break


def _openai_stream(r: requests.Response) -> Iterator[str]:
    """SSE: các dòng 'data: {json}' ... kết thúc bằng 'data: [DONE]'."""
    for line in r.iter_lines():
        line = line.decode('utf-8')  # tự giải mã, KHÔNG dùng decode_unicode
        if not line.startswith('data: '):
            continue
        data = line[len('data: '):]
        if data == '[DONE]':
            break
        delta = json.loads(data)['choices'][0].get('delta', {})
        if delta.get('content'):
            yield delta['content']


def _word_stream(text: str) -> Iterator[str]:
    """Giả lập stream cho chế độ demo: trả từng từ một."""
    words = text.split(' ')
    for i, word in enumerate(words):
        yield word + (' ' if i < len(words) - 1 else '')
