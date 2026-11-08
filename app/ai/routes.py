import functools
import json
import re
from pathlib import Path
from flask import (Response, abort, current_app, flash, jsonify, redirect,
                   render_template, request, session, stream_with_context,
                   url_for)
from markdown_it import MarkdownIt
from markupsafe import Markup, escape
from app import db
from app.models import Product
from app.utils import vnd
from app.ai import bp, prompts, rag, writing
from app.ai.embeddings import EmbeddingError
from app.ai.guard import check_rate, clean_input, looks_like_injection
from app.ai.llm import LLMClient, LLMError

AI_ERRORS = (LLMError, EmbeddingError)

SEARCH_MODES = {
    'hybrid': 'Lai (ngữ nghĩa + từ khóa)',
    'semantic': 'Ngữ nghĩa (embedding)',
    'keyword': 'Từ khóa',
    'compare': 'So sánh: từ khóa | ngữ nghĩa',
}


def access(view):
    """AI_REQUIRE_LOGIN=1 -> chỉ người đã đăng nhập (Flask-Login) được dùng AI."""
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if current_app.config['AI_REQUIRE_LOGIN']:
            from flask_login import current_user
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
        return view(*args, **kwargs)
    return wrapper


@bp.context_processor
def inject_ai_info() -> dict:
    """Biến dùng trong template ai/: có đang ở chế độ demo không..."""
    cfg = current_app.config
    demo = cfg['LLM_PROVIDER'] == 'demo'
    llm = 'demo' if demo else f"{cfg['LLM_PROVIDER']}:{cfg['LLM_MODEL']}"
    return {'ai_demo': demo, 'ai_llm': llm,
            'ai_embed': rag.get_embedder().name}


@bp.app_template_filter('cite_links')
def cite_links(text: str, citations: list[dict]) -> Markup:
    """Đổi [n] trong câu trả lời thành link tới nguồn n (sau khi escape HTML)."""
    urls = {str(c['n']): c['url'] for c in citations}
    html = str(escape(text))
    html = re.sub(r'\[(\d+)\]', lambda m: (
        f'<a href="{urls[m.group(1)]}">[{m.group(1)}]</a>'
        if m.group(1) in urls else m.group(0)), html)
    return Markup(html)


def card(p: Product, hit=None) -> dict:
    """Sản phẩm -> dict đơn giản cho template/JSON (template không phải biết model)."""
    d = {'id': p.id, 'name': p.name, 'url': rag.product_url(p.id),
         'image': getattr(p, 'image_url', None),
         'category': p.category.name if p.category else None,
         'price': p.price, 'price_text': vnd(p.price),
         'in_stock': bool(p.in_stock),
         'description': ' '.join((p.description or '').split())[:140]}
    if hit is not None:
        d.update(score=round(hit.score, 3), semantic=round(hit.semantic, 3),
                 keyword=round(hit.keyword, 3))
    return d


def too_fast_json():
    return jsonify(error='Bạn thao tác quá nhanh, thử lại sau.'), 429


# ------------------------- Tìm kiếm sản phẩm (ngữ nghĩa) --------------------
def _search(query: str, mode: str) -> dict[str, list[dict]]:
    modes = ['keyword', 'semantic'] if mode == 'compare' else [mode]
    return {m: [card(p, h) for p, h in rag.search_products(query, m)]
            for m in modes}


@bp.route('/search')
@access
def search():
    q = clean_input(request.args.get('q', ''))
    mode = request.args.get('mode', 'hybrid')
    if mode not in SEARCH_MODES:
        mode = 'hybrid'
    results: dict[str, list] = {}
    if q:
        if not check_rate():
            flash('Bạn tìm quá nhanh, vui lòng đợi một chút.')
        else:
            try:
                results = _search(q, mode)
            except AI_ERRORS as e:
                flash(f'Lỗi dịch vụ AI: {e}')
    return render_template('ai/search.html', title='Tìm sản phẩm thông minh',
                           q=q, mode=mode, modes=SEARCH_MODES, results=results)


@bp.route('/api/search')
@access
def api_search():
    """GET /ai/api/search?q=&mode=hybrid|semantic|keyword&k=8 -> JSON sản phẩm."""
    q = clean_input(request.args.get('q', ''))
    mode = request.args.get('mode', 'hybrid')
    if not q or mode not in ('hybrid', 'semantic', 'keyword'):
        return jsonify(error='Thiếu q hoặc mode không hợp lệ'), 400
    if not check_rate():
        return too_fast_json()
    k = min(max(request.args.get('k', 8, type=int), 1), 20)
    try:
        hits = rag.search_products(q, mode, k)
    except AI_ERRORS as e:
        return jsonify(error=str(e)), 503
    return jsonify(query=q, mode=mode, items=[card(p, h) for p, h in hits])


@bp.route('/api/products/<int:id>/similar')
@access
def api_similar(id):
    """Sản phẩm tương tự (láng giềng gần nhất theo embedding)."""
    p = db.get_or_404(Product, id)
    if not p.is_active:
        return jsonify(error='Không tìm thấy sản phẩm'), 404
    if not check_rate():
        return too_fast_json()
    try:
        hits = rag.similar_products(id, int(request.args.get('k', 4)))
    except AI_ERRORS as e:
        return jsonify(error=str(e)), 503
    return jsonify(items=[card(x, h) for x, h in hits])


@bp.route('/api/products/<int:id>/summary')
@access
def api_summary(id):
    """Tóm tắt sản phẩm thành một câu (LLM; có cache)."""
    p = db.get_or_404(Product, id)
    if not p.is_active:
        return jsonify(error='Không tìm thấy sản phẩm'), 404
    if not check_rate():
        return too_fast_json()
    try:
        return jsonify(text=writing.summarize_product(rag.product_text(p)))
    except AI_ERRORS as e:
        return jsonify(error=str(e)), 503


# ------------------------------ Trợ lý mua sắm -------------------------------
@bp.route('/assistant')
@access
def assistant():
    """Trang hỏi đáp: GET /ai/assistant?q=... (GET -> không vướng CSRF, dễ chia sẻ)."""
    q = clean_input(request.args.get('q', ''))
    history = session.get('ai_history', [])
    result = None
    if q:
        if not check_rate():
            flash('Bạn hỏi quá nhanh, vui lòng đợi một chút.')
            return redirect(url_for('ai.assistant'))
        try:
            result = rag.answer(q, history)
        except AI_ERRORS as e:
            flash(f'Lỗi dịch vụ AI: {e}')
            return redirect(url_for('ai.assistant'))
        result['question'] = q
        if not result['refused']:  # không đưa câu bị chặn vào lịch sử
            session['ai_history'] = (history + [
                {'q': q, 'a': result['answer'][:400]}])[-3:]
    return render_template('ai/assistant.html', title='Trợ lý mua sắm',
                           q=q, result=result, history=history)


@bp.route('/assistant/clear')
@access
def assistant_clear():
    session.pop('ai_history', None)
    return redirect(url_for('ai.assistant'))


@bp.route('/api/ask')
@access
def api_ask():
    """GET /ai/api/ask?q=... -> {answer, citations, refused, blocked} (không lưu lịch sử)."""
    q = clean_input(request.args.get('q', ''))
    if not q:
        return jsonify(error='Thiếu câu hỏi (q)'), 400
    if not check_rate():
        return too_fast_json()
    try:
        return jsonify(rag.answer(q))
    except AI_ERRORS as e:
        return jsonify(error=str(e)), 503


def sse(data: dict, event: str | None = None) -> str:
    """Định dạng một sự kiện Server-Sent Events."""
    head = f'event: {event}\n' if event else ''
    return f'{head}data: {json.dumps(data, ensure_ascii=False)}\n\n'


@bp.route('/assistant/stream')
@access
def assistant_stream():
    """Trả lời dạng stream (SSE): meta (nguồn) -> nhiều delta -> done {refused}."""
    question = clean_input(request.args.get('q', ''))
    if not question:
        abort(400)
    if not check_rate():
        return Response(sse({'error': 'Quá giới hạn tần suất'}, 'llm_error'),
                        429, mimetype='text/event-stream')
    if looks_like_injection(question):
        citations, blocked, messages = [], 0, None
    else:
        try:
            messages, citations, blocked = rag.prepare(
                question, session.get('ai_history'))
        except AI_ERRORS as e:
            return Response(sse({'error': str(e)}, 'llm_error'), 503,
                            mimetype='text/event-stream')
    product_response = (rag.product_lookup_response(question, messages)
                        if messages is not None else None)

    def generate():
        # Nguồn được gửi TRƯỚC khi LLM trả lời; nếu rốt cuộc LLM từ chối thì sự kiện
        # 'done' mang refused=true để trình duyệt xóa danh sách nguồn đã hiện.
        yield sse({'citations': citations, 'blocked': blocked}, 'meta')
        refused = True
        if messages is None:
            yield sse({'delta': rag.REFUSE_INJECTION})
        elif product_response is not None:
            yield sse({'delta': product_response})
            refused = product_response == rag.PRODUCT_NOT_FOUND
        elif not citations:
            yield sse({'delta': prompts.NO_ANSWER})
        else:
            parts = []
            try:
                for piece in LLMClient.from_config().chat(messages, True):
                    parts.append(piece)
                    yield sse({'delta': piece})
                refused = prompts.NO_ANSWER in ''.join(parts)
            except LLMError as e:
                yield sse({'error': str(e)}, 'llm_error')
        yield sse({'refused': refused}, 'done')

    return Response(stream_with_context(generate()),
                    mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


# ------------------------ Xem tài liệu hướng dẫn ---------------------------
def _docs_dir() -> Path:
    return Path(current_app.config['AI_DOCS_DIR'])


@bp.route('/docs/')
@bp.route('/docs/<name>')
def doc(name: str = 'tro-ly-ai'):
    path = _docs_dir() / f'{name}.md'
    if not re.fullmatch(r'[\w-]+', name) or not path.is_file():
        abort(404)
    md = MarkdownIt('commonmark', {'html': False}).enable('table')
    html = md.render(path.read_text(encoding='utf-8'))
    docs = [(p.stem, p.read_text(encoding='utf-8').splitlines()[0].lstrip('# '))
            for p in sorted(_docs_dir().glob('*.md'))]
    return render_template('ai/doc.html', title='Hướng dẫn', html=Markup(html),
                           docs=docs, current=name)
