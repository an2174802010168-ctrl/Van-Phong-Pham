"""Mock LLM server – giả lập API của Ollama và OpenAI để test khi chưa có LLM/khóa API.

Chỉ dùng thư viện chuẩn. Kiểm tra request đúng schema (sai -> lỗi 400/401 như
server thật) và trả response đúng định dạng chính thức:
  Ollama : POST /api/chat (stream NDJSON hoặc không), POST /api/embed
  OpenAI : POST /v1/chat/completions (stream SSE hoặc không), POST /v1/embeddings
           (nhận mọi tiền tố, vd /v1beta/openai/chat/completions như Gemini)
Câu trả lời là văn bản "(mock)" cố định – KHÔNG phải LLM thật.

Chạy:  python tools/mock_llm_server.py --port 8808
Rồi trong .env của FlaskShop:
  LLM_PROVIDER=ollama  LLM_BASE_URL=http://localhost:8808
  hoặc LLM_PROVIDER=openai LLM_BASE_URL=http://localhost:8808/v1 LLM_API_KEY=test
"""
import argparse
import hashlib
import json
import math
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIM = 64  # số chiều vector embedding giả
ROLES = {'system', 'user', 'assistant', 'tool'}


# ----------------------------- Nội dung giả -------------------------------
def fake_answer(messages: list[dict]) -> str:
    """Câu trả lời cố định, có nhắc lại câu hỏi và một trích dẫn [1]."""
    last = messages[-1]['content']
    question = last.rsplit('CÂU HỎI:', 1)[-1].strip().splitlines()[-1]
    return (f'(mock) Đã nhận {len(messages)} tin nhắn. '
            f'Câu hỏi: "{question[:80]}". Đây là câu trả lời thử [1].')


def fake_embedding(text: str) -> list[float]:
    """Vector 'băm từ' (feature hashing): câu chung nhiều từ -> cosine cao."""
    vec = [0.0] * DIM
    for word in re.findall(r'\w+', text.lower()):
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        vec[h % DIM] += 1.0 if (h >> 8) % 2 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def pieces(text: str) -> list[str]:
    """Chia câu trả lời thành các mẩu nhỏ để stream."""
    words = text.split(' ')
    return [w + (' ' if i < len(words) - 1 else '') for i, w in enumerate(words)]


# ----------------------------- Kiểm tra schema ----------------------------
def check_chat(body: dict) -> str | None:
    """Trả về thông báo lỗi nếu body không đúng schema chat (Ollama/OpenAI)."""
    if not isinstance(body.get('model'), str) or not body['model']:
        return 'model is required'
    msgs = body.get('messages')
    if not isinstance(msgs, list) or not msgs:
        return 'messages must be a non-empty list'
    for m in msgs:
        if not isinstance(m, dict) or m.get('role') not in ROLES \
                or not isinstance(m.get('content'), str):
            return f'invalid message: {str(m)[:80]}'
    if 'stream' in body and not isinstance(body['stream'], bool):
        return 'stream must be a boolean'
    return None


def check_embed(body: dict) -> str | None:
    if not isinstance(body.get('model'), str) or not body['model']:
        return 'model is required'
    inp = body.get('input')
    if isinstance(inp, str) or (isinstance(inp, list) and inp and
                                all(isinstance(s, str) for s in inp)):
        return None
    return 'input must be a string or a list of strings'


# ----------------------------- HTTP handler -------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = 'MockLLM/1.0'

    def log_message(self, fmt, *args):  # in gọn từng request ra terminal
        pass

    def _log(self, body: dict, note: str = '') -> None:
        info = f"model={body.get('model')}"
        if 'messages' in body:
            info += f" messages={len(body['messages'])}"
        if 'input' in body:
            n = 1 if isinstance(body['input'], str) else len(body['input'])
            info += f' input={n}'
        if 'stream' in body:
            info += f" stream={str(body['stream']).lower()}"
        if not self.server.quiet:
            print(f'[mock] {self.command} {self.path}  {info} {note}',
                  flush=True)
        self.server.requests.append({'path': self.path, 'body': body,
                                     'headers': dict(self.headers)})

    def _json(self, status: int, data: dict) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _start_stream(self, content_type: str) -> None:
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.end_headers()  # HTTP/1.0: đóng kết nối = hết stream

    def _send_line(self, text: str) -> None:
        self.wfile.write(text.encode('utf-8'))
        self.wfile.flush()

    def do_GET(self):
        if self.path in ('/', ''):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Mock LLM server is running')
        else:
            self._json(404, {'error': 'not found'})

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(length) or b'{}')
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {'error': 'invalid JSON body'})
        path = self.path.split('?')[0]
        if path == '/api/chat':
            return self.ollama_chat(body)
        if path == '/api/embed':
            return self.ollama_embed(body)
        if path.endswith('/chat/completions'):
            return self.openai_chat(body)
        if path.endswith('/embeddings'):
            return self.openai_embed(body)
        self._json(404, {'error': f'unknown endpoint {path}'})

    # ------------------------------ Ollama --------------------------------
    def ollama_chat(self, body: dict):
        error = check_chat(body)
        self._log(body, f'-> 400 {error}' if error else '')
        if error:
            return self._json(400, {'error': error})
        text, model = fake_answer(body['messages']), body['model']
        now = datetime.now(timezone.utc).isoformat()
        final = {'model': model, 'created_at': now, 'done': True,
                 'done_reason': 'stop', 'total_duration': 1000000,
                 'load_duration': 1000, 'prompt_eval_count': 10,
                 'eval_count': len(pieces(text))}
        if body.get('stream', True) is False:  # Ollama mặc định stream=true
            final['message'] = {'role': 'assistant', 'content': text}
            return self._json(200, final)
        self._start_stream('application/x-ndjson')
        for p in pieces(text):
            chunk = {'model': model, 'created_at': now, 'done': False,
                     'message': {'role': 'assistant', 'content': p}}
            self._send_line(json.dumps(chunk, ensure_ascii=False) + '\n')
            time.sleep(self.server.delay)
        final['message'] = {'role': 'assistant', 'content': ''}
        self._send_line(json.dumps(final) + '\n')

    def ollama_embed(self, body: dict):
        error = check_embed(body)
        self._log(body, f'-> 400 {error}' if error else '')
        if error:
            return self._json(400, {'error': error})
        inputs = [body['input']] if isinstance(body['input'], str) \
            else body['input']
        self._json(200, {'model': body['model'],
                         'embeddings': [fake_embedding(t) for t in inputs],
                         'total_duration': 1000, 'load_duration': 100,
                         'prompt_eval_count': len(inputs)})

    # ------------------------------ OpenAI --------------------------------
    def _check_key(self, body: dict) -> bool:
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Bearer ') and auth[7:].strip() not in ('', 'None'):
            return True
        self._log(body, '-> 401 missing API key')
        self._json(401, {'error': {
            'message': 'Incorrect API key provided.',
            'type': 'invalid_request_error', 'code': 'invalid_api_key'}})
        return False

    def openai_chat(self, body: dict):
        if not self._check_key(body):
            return
        error = check_chat(body)
        self._log(body, f'-> 400 {error}' if error else '')
        if error:
            return self._json(400, {'error': {
                'message': error, 'type': 'invalid_request_error'}})
        text, model = fake_answer(body['messages']), body['model']
        base = {'id': 'chatcmpl-mock123', 'created': int(time.time()),
                'model': model}
        if not body.get('stream'):  # OpenAI mặc định stream=false
            message = {'role': 'assistant', 'content': text}
            return self._json(200, {
                **base, 'object': 'chat.completion',
                'choices': [{'index': 0, 'finish_reason': 'stop',
                             'message': message}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 20,
                          'total_tokens': 30}})
        self._start_stream('text/event-stream')
        for i, p in enumerate(pieces(text)):
            delta = {'role': 'assistant', 'content': p} if i == 0 \
                else {'content': p}
            self._sse({**base, 'object': 'chat.completion.chunk', 'choices': [
                {'index': 0, 'delta': delta, 'finish_reason': None}]})
            time.sleep(self.server.delay)
        self._sse({**base, 'object': 'chat.completion.chunk', 'choices': [
            {'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})
        self._send_line('data: [DONE]\n\n')

    def _sse(self, data: dict) -> None:
        self._send_line(f'data: {json.dumps(data, ensure_ascii=False)}\n\n')

    def openai_embed(self, body: dict):
        if not self._check_key(body):
            return
        error = check_embed(body)
        self._log(body, f'-> 400 {error}' if error else '')
        if error:
            return self._json(400, {'error': {
                'message': error, 'type': 'invalid_request_error'}})
        inputs = [body['input']] if isinstance(body['input'], str) \
            else body['input']
        data = [{'object': 'embedding', 'index': i,
                 'embedding': fake_embedding(t)} for i, t in enumerate(inputs)]
        self._json(200, {'object': 'list', 'model': body['model'],
                         'data': data,
                         'usage': {'prompt_tokens': len(inputs),
                                   'total_tokens': len(inputs)}})


# ----------------------------- Khởi động ----------------------------------
def make_server(port: int = 8808, delay: float = 0.02) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.requests = []   # lưu các request đã nhận (để test kiểm tra)
    server.delay = delay   # độ trễ giữa các mẩu khi stream (giây)
    server.quiet = False   # True: không in log từng request
    return server


def serve_in_thread(port: int = 0, delay: float = 0.0) -> ThreadingHTTPServer:
    """Chạy server ở luồng nền (port=0: hệ điều hành chọn cổng trống)."""
    server = make_server(port, delay)
    server.quiet = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--port', type=int, default=8808)
    parser.add_argument('--delay', type=float, default=0.05)
    args = parser.parse_args()
    print(f'Mock LLM server: http://localhost:{args.port}  '
          '(Ollama /api/*, OpenAI /v1/*) – Ctrl+C để dừng', flush=True)
    try:
        make_server(args.port, args.delay).serve_forever()
    except KeyboardInterrupt:
        pass
