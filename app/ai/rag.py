"""Pipeline RAG cho cửa hàng: chunk -> embed -> lưu -> truy hồi -> prompt có ngữ cảnh
-> LLM trả lời có trích dẫn [n].

Hai nguồn tri thức:
  'product' : mỗi sản phẩm đang bán = 1 đoạn (tên, danh mục, giá, tình trạng, mô tả)
  'doc'     : các tệp hướng dẫn *.md trong app/ai/docs (đặt hàng, thanh toán, API...)

Nguyên tắc quan trọng với cửa hàng: vector chỉ dùng để TÌM sản phẩm; còn GIÁ và
TÌNH TRẠNG đưa vào prompt luôn đọc lại từ CSDL tại thời điểm trả lời (Context.text),
nên LLM không bao giờ trích giá cũ.
"""
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
import sqlalchemy as sa
from flask import current_app, url_for
from werkzeug.routing import BuildError
from app import db
from app.models import Product
from app.utils import vnd
from app.ai import prompts
from app.ai.chunking import Chunk, chunk_markdown
from app.ai.embeddings import Embedder
from app.ai.filters import PriceRange, parse_price, remove_price
from app.ai.demo import parse_prompt, product_fields
from app.ai.guard import filter_contexts, looks_like_injection
from app.ai.keywords import product_match
from app.ai.llm import LLMClient
from app.ai.vectorstore import Hit, VectorStore

REFUSE_INJECTION = ('Yêu cầu bị chặn: câu hỏi có dấu hiệu prompt injection '
                    '(cố thay đổi chỉ dẫn của trợ lý).')
PRODUCT_NOT_FOUND = 'Xin lỗi, tôi không tìm thấy sản phẩm phù hợp với yêu cầu.'
EMBED_MAX_CHARS = 1500  # cắt mô tả quá dài trước khi embedding


def get_embedder() -> Embedder:
    return Embedder.from_config()


def get_store() -> VectorStore:
    return VectorStore(get_embedder().name)


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode('utf-8')).hexdigest()


# --------------------------- Văn bản của sản phẩm ---------------------------
def product_text(p: Product) -> str:
    """Văn bản đầy đủ của sản phẩm (đưa vào prompt + chấm từ khóa + băm).
    Mỗi trường một dòng 'Nhãn: giá trị' để demo.product_fields đọc lại được."""
    lines = [f'Tên: {p.name}']
    if p.category:
        lines.append(f'Danh mục: {p.category.name}')
    lines.append(f'Giá: {vnd(p.price)}')
    lines.append('Tình trạng: ' + ('Còn hàng' if p.in_stock else 'Hết hàng'))
    if p.description:
        lines.append('Mô tả: ' + ' '.join(p.description.split()))
    return '\n'.join(lines)


def embed_text(p: Product) -> str:
    """Văn bản để embedding: bỏ giá/tình trạng (con số làm nhiễu ngữ nghĩa)."""
    parts = [p.name, p.category.name if p.category else '', p.description or '']
    return '\n'.join(x for x in parts if x)[:EMBED_MAX_CHARS]


def product_url(product_id: int) -> str:
    """Link tới trang sản phẩm. Mặc định api.product; đặt AI_PRODUCT_ENDPOINT
    (và AI_PRODUCT_ARG) để trỏ tới trang chi tiết thật của shop."""
    cfg = current_app.config
    try:
        return url_for(cfg['AI_PRODUCT_ENDPOINT'],
                       **{cfg['AI_PRODUCT_ARG']: product_id})
    except BuildError:
        return url_for('api.product', id=product_id)


# ------------------------- Đánh chỉ mục (indexing) -------------------------
def index_product(p: Product) -> int:
    """Embedding một sản phẩm (ngừng bán -> xóa khỏi kho vector)."""
    store = get_store()
    if not p.is_active:
        return store.delete('product', str(p.id))
    text = product_text(p)
    vec = get_embedder().embed([embed_text(p)])
    return store.upsert('product', str(p.id), [Chunk(p.name, text)], vec,
                        content_hash=_sha(text))


def safe_index_product(p: Product) -> None:
    """Gọi sau khi admin thêm/sửa sản phẩm: lỗi AI không được làm hỏng việc lưu.
    (Không bắt buộc – AI_AUTO_SYNC cũng tự cập nhật sau tối đa AI_SYNC_TTL giây.)"""
    try:
        index_product(p)
    except Exception:
        current_app.logger.exception('Không index được sản phẩm %s', p.id)


def sync_products(rebuild: bool = False, batch: int = 32) -> dict[str, int]:
    """Đồng bộ kho vector với bảng sản phẩm, chỉ embed phần thay đổi:
    mới -> thêm ; nội dung đổi (băm khác) -> làm lại ; ngừng bán/bị xóa -> bỏ."""
    store, embedder = get_store(), get_embedder()
    if rebuild:
        store.delete('product')
    indexed = store.hashes('product')
    products = list(db.session.scalars(
        sa.select(Product).where(Product.is_active.is_(True))))
    todo, added, updated = [], 0, 0
    for p in products:
        text = product_text(p)
        old = indexed.get(str(p.id), 'MISSING')
        if old == 'MISSING':
            added += 1
        elif old != _sha(text):
            updated += 1
        else:
            continue
        todo.append((p, text))
    active = {str(p.id) for p in products}
    removed = [ref for ref in indexed if ref not in active]
    for ref in removed:
        store.delete('product', ref)
    for i in range(0, len(todo), batch):
        part = todo[i:i + batch]
        vectors = embedder.embed([embed_text(p) for p, _ in part])
        for (p, text), vec in zip(part, vectors):
            store.upsert('product', str(p.id), [Chunk(p.name, text)],
                         vec[None, :], content_hash=_sha(text))
    return {'added': added, 'updated': updated, 'removed': len(removed),
            'unchanged': len(products) - added - updated}


def index_docs(folder: str | None = None, force: bool = False
               ) -> tuple[int, int]:
    """Index các tệp *.md trong thư mục tài liệu. Tệp không đổi (băm giống) thì bỏ qua.
    Trả về (số tệp, số đoạn vừa index)."""
    folder = Path(folder or current_app.config['AI_DOCS_DIR'])
    store, embedder = get_store(), get_embedder()
    files = sorted(folder.glob('*.md'))
    indexed = store.hashes('doc')
    for ref in set(indexed) - {f.stem for f in files}:
        store.delete('doc', ref)  # tệp đã bị xóa khỏi thư mục
    total = 0
    for path in files:
        md = path.read_text(encoding='utf-8')
        if not force and indexed.get(path.stem) == _sha(md):
            continue
        chunks = chunk_markdown(md)
        vectors = embedder.embed([f'{c.title}\n{c.text}' for c in chunks])
        total += store.upsert('doc', path.stem, chunks, vectors,
                              content_hash=_sha(md))
    return len(files), total


def ensure_fresh() -> None:
    """Tự đồng bộ kho vector (tài liệu + sản phẩm) tối đa mỗi AI_SYNC_TTL giây.
    Lỗi (vd. dịch vụ embedding tắt) chỉ ghi log – không làm hỏng yêu cầu của khách."""
    cfg = current_app.config
    if not cfg['AI_AUTO_SYNC']:
        return
    state = current_app.extensions.setdefault('ai', {'synced_at': None})
    now = time.monotonic()
    if state['synced_at'] is not None and \
            now - state['synced_at'] < cfg['AI_SYNC_TTL']:
        return
    state['synced_at'] = now  # đặt trước: lỗi cũng không thử lại dồn dập
    try:
        index_docs()
        sync_products()
    except Exception:
        current_app.logger.exception('Đồng bộ kho vector AI thất bại')


# ------------------------- Truy hồi (retrieval) ----------------------------
def product_filter(price: PriceRange):
    """Hàm `keep` cho kho vector: chỉ giữ sản phẩm đang bán và trong khoảng giá;
    đoạn tài liệu luôn được giữ."""
    stmt = price.apply(sa.select(Product.id).where(Product.is_active.is_(True)),
                       Product.price)
    allowed = {str(i) for i in db.session.scalars(stmt)}
    return lambda c: c.source != 'product' or c.ref_id in allowed


def retrieve(query: str, k: int | None = None,
             sources: list[str] | str | None = None) -> list[Hit]:
    """Tìm k đoạn liên quan nhất (lai: cosine + từ khóa), đã áp bộ lọc giá."""
    cfg = current_app.config
    ensure_fresh()
    price = parse_price(query)
    text = remove_price(query)
    qvec = get_embedder().embed([text])[0]
    return get_store().hybrid_search(
        text, qvec, k or cfg['AI_TOP_K'], source=sources,
        alpha=cfg['AI_HYBRID_ALPHA'], min_score=cfg['AI_MIN_SCORE'],
        keep=product_filter(price))


@dataclass
class Context:
    """Một đoạn ngữ cảnh đã sẵn sàng đưa vào prompt (sản phẩm: dữ liệu mới nhất)."""
    source: str           # 'product' | 'doc'
    ref_id: str
    label: str
    text: str
    score: float
    semantic: float = 0.0
    keyword: float = 0.0
    product: Product | None = None


def to_contexts(hits: list[Hit]) -> list[Context]:
    """Hit -> Context. Sản phẩm: đọc lại từ CSDL (giá/tồn kho hiện tại); bỏ sản phẩm
    đã ngừng bán/bị xóa kể từ lần index; loại bản trùng."""
    ids = [int(h.chunk.ref_id) for h in hits if h.chunk.source == 'product']
    products = {p.id: p for p in db.session.scalars(sa.select(Product).where(
        Product.id.in_(ids), Product.is_active.is_(True)))} if ids else {}
    out, seen = [], set()
    for h in hits:
        c = h.chunk
        if (c.source, c.ref_id, c.chunk_index) in seen:
            continue
        seen.add((c.source, c.ref_id, c.chunk_index))
        if c.source == 'product':
            p = products.get(int(c.ref_id))
            if p is None:
                continue
            out.append(Context('product', c.ref_id, f'Sản phẩm «{p.name}»',
                               product_text(p), h.score, h.semantic,
                               h.keyword, p))
        else:
            out.append(Context('doc', c.ref_id,
                               f'Tài liệu «{c.title}» ({c.ref_id}.md)', c.text,
                               h.score, h.semantic, h.keyword))
    return out


def fit_contexts(items: list[Context], max_chars: int | None = None
                 ) -> list[Context]:
    """Giữ các đoạn đầu tiên sao cho tổng độ dài <= max_chars (giới hạn token)."""
    max_chars = max_chars or current_app.config['AI_MAX_CONTEXT_CHARS']
    kept, used = [], 0
    for item in items:
        if used + len(item.text) > max_chars:
            break
        kept.append(item)
        used += len(item.text)
    return kept


def make_citation(n: int, ctx: Context) -> dict:
    """Thông tin nguồn [n] để hiển thị và dẫn link."""
    if ctx.source == 'doc':
        url = url_for('ai.doc', name=ctx.ref_id)
    else:
        url = product_url(int(ctx.ref_id))
    return {'n': n, 'label': ctx.label, 'url': url,
            'snippet': ctx.text[:160], 'score': round(ctx.score, 3)}


def is_product_lookup(query: str) -> bool:
    """Keep product lookups from being answered using unrelated documents."""
    normalized = query.casefold()
    policy_terms = ('thanh toán', 'đặt hàng', 'giao hàng', 'vận chuyển',
                    'đổi trả', 'bảo hành', 'đơn hàng', 'phí ship', 'cod')
    if any(term in normalized for term in policy_terms):
        return False
    return any(term in normalized for term in (
        'sản phẩm', 'mặt hàng', 'tìm', 'gợi ý', 'đề xuất', 'tư vấn',
        'loại nào', 'mẫu nào', 'mua', 'có '))


def product_lookup_response(query: str, messages: list[dict]) -> str | None:
    """Build product answers from matched catalog data, not generated claims."""
    if not is_product_lookup(query):
        return None
    _, contexts = parse_prompt(messages[-1]['content'])
    products = [(n, product_fields(body)) for n, body in contexts]
    products = [(n, fields) for n, fields in products if fields.get('Tên')]
    if not products:
        return PRODUCT_NOT_FOUND
    lines = [
        f"- {fields['Tên']} – {fields.get('Giá', '?')} – "
        f"{fields.get('Tình trạng', '?')} [{n}]"
        for n, fields in products
    ]
    return f'Tìm thấy {len(products)} sản phẩm phù hợp:\n' + '\n'.join(lines)


# ------------------------- Dựng prompt & trả lời ---------------------------
def build_messages(query: str, contexts: list[Context],
                   history: list[dict] | None = None,
                   max_chars: int | None = None) -> list[dict]:
    """messages = [system] + lịch sử ngắn + [user: ngữ cảnh đánh số + câu hỏi]."""
    contexts = fit_contexts(contexts, max_chars)
    blocks = [f'[{i}] {c.label}\n{c.text}'
              for i, c in enumerate(contexts, start=1)]
    user = (f'{prompts.CONTEXT_HEADER}\n<context>\n' + '\n\n'.join(blocks) +
            f'\n</context>\n\nCÂU HỎI: {query}')
    messages = [{'role': 'system', 'content': prompts.SYSTEM_RAG}]
    for turn in (history or [])[-3:]:  # tối đa 3 lượt gần nhất
        messages.append({'role': 'user', 'content': turn['q']})
        messages.append({'role': 'assistant', 'content': turn['a']})
    messages.append({'role': 'user', 'content': user})
    return messages


def prepare(query: str, history: list[dict] | None = None):
    """Truy hồi -> dữ liệu mới nhất -> lọc injection -> cắt theo giới hạn -> messages."""
    contexts = to_contexts(retrieve(query, sources=['doc', 'product']))
    safe, blocked = filter_contexts(contexts)
    searchable_query = remove_price(query)
    matching_products = []
    for ctx in safe:
        product = ctx.product
        if ctx.source != 'product' or product is None:
            continue
        fields = {
            'Tên': product.name,
            'Danh mục': product.category.name if product.category else '',
            'Mô tả': product.description or '',
        }
        if product_match(searchable_query, fields):
            matching_products.append(ctx)
    if is_product_lookup(query):
        safe = matching_products
    else:
        safe = [ctx for ctx in safe
                if ctx.source != 'product' or ctx in matching_products]
    safe = fit_contexts(safe)
    citations = [make_citation(i, c) for i, c in enumerate(safe, start=1)]
    return build_messages(query, safe, history), citations, len(blocked)


def answer(query: str, history: list[dict] | None = None) -> dict:
    """Trả lời câu hỏi: {answer, citations, blocked, refused}."""
    if looks_like_injection(query):
        return {'answer': REFUSE_INJECTION, 'citations': [], 'blocked': 0,
                'refused': True}
    messages, citations, blocked = prepare(query, history)
    if not citations:  # không có ngữ cảnh -> từ chối, khỏi tốn lượt gọi LLM
        response = product_lookup_response(query, messages)
        return {'answer': response or prompts.NO_ANSWER, 'citations': [],
                'blocked': blocked, 'refused': True}
    response = product_lookup_response(query, messages)
    if response is not None:
        return {'answer': response, 'citations': citations,
                'blocked': blocked, 'refused': False}
    text = LLMClient.from_config().chat(messages)
    refused = prompts.NO_ANSWER in text  # LLM tự nhận là không có thông tin
    return {'answer': text, 'citations': [] if refused else citations,
            'blocked': blocked, 'refused': refused}


# ---------------------- Tìm kiếm & gợi ý sản phẩm --------------------------
SEARCH_ALPHA = {'keyword': 0.0, 'semantic': 1.0}  # 'hybrid' lấy từ config


def _with_products(hits: list[Hit]) -> list[tuple[Product, Hit]]:
    """Ghép Hit với Product (giữ thứ tự xếp hạng, bỏ sản phẩm không còn bán)."""
    ids = [int(h.chunk.ref_id) for h in hits]
    products = {p.id: p for p in db.session.scalars(sa.select(Product).where(
        Product.id.in_(ids), Product.is_active.is_(True)))} if ids else {}
    out, seen = [], set()
    for h in hits:
        pid = int(h.chunk.ref_id)
        if pid in products and pid not in seen:
            seen.add(pid)
            out.append((products[pid], h))
    return out


def search_products(query: str, mode: str = 'hybrid',
                    k: int = 8) -> list[tuple[Product, Hit]]:
    """Tìm sản phẩm theo 3 kiểu: keyword | semantic | hybrid.
    Hiểu cả điều kiện giá trong câu ("giày chạy bộ dưới 1 triệu")."""
    cfg = current_app.config
    ensure_fresh()
    alpha = SEARCH_ALPHA.get(mode, cfg['AI_HYBRID_ALPHA'])
    # keyword: chỉ lấy sản phẩm có khớp từ ; semantic: luôn trả top-k để xem điểm
    min_score = {'keyword': 0.01, 'semantic': 0.0}.get(mode, cfg['AI_MIN_SCORE'])
    text = remove_price(query)
    qvec = get_embedder().embed([text])[0]
    hits = get_store().hybrid_search(
        text, qvec, k, source='product', alpha=alpha, min_score=min_score,
        keep=product_filter(parse_price(query)))
    return _with_products(hits)


def similar_products(product_id: int, k: int = 4) -> list[tuple[Product, Hit]]:
    """Sản phẩm tương tự = láng giềng gần nhất trong không gian vector."""
    ensure_fresh()
    near = get_store().neighbors('product', str(product_id), k,
                                 keep=product_filter(PriceRange()))
    return _with_products([Hit(c, s, s) for c, s in near])
