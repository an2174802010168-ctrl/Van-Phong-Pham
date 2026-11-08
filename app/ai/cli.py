"""Lệnh CLI: flask ai index-docs | index-products [--rebuild] | ask "..." | stats | describe"""
import functools
import click
from flask import current_app
from sqlalchemy.exc import OperationalError
from app.ai import bp, prompts, rag, writing
from app.ai.embeddings import EmbeddingError
from app.ai.guard import looks_like_injection
from app.ai.llm import LLMClient, LLMError


def friendly_errors(command):
    """Đổi lỗi thường gặp thành thông báo ngắn thay vì traceback dài."""
    @functools.wraps(command)
    def wrapper(*args, **kwargs):
        try:
            return command(*args, **kwargs)
        except (LLMError, EmbeddingError) as e:
            raise click.ClickException(str(e))
        except OperationalError as e:
            raise click.ClickException(
                f'Lỗi CSDL ({e.orig}). Đã chạy "flask db upgrade" chưa?')
    return wrapper


@bp.cli.command('index-docs')
@click.option('--folder', default=None, help='Thư mục chứa *.md')
@click.option('--force', is_flag=True, help='Index lại cả tệp không đổi')
@friendly_errors
def index_docs_cmd(folder, force):
    """Chia đoạn + embedding các tài liệu hướng dẫn (tệp không đổi thì bỏ qua)."""
    files, chunks = rag.index_docs(folder, force=force)
    click.echo(f'{files} tài liệu, {chunks} đoạn mới/đổi '
               f'(embedding: {rag.get_embedder().name})')


@bp.cli.command('index-products')
@click.option('--rebuild', is_flag=True, help='Xóa vector cũ, index lại hết')
@friendly_errors
def index_products_cmd(rebuild):
    """Đồng bộ vector sản phẩm (chỉ embed phần mới/đổi; --rebuild: làm lại hết)."""
    r = rag.sync_products(rebuild=rebuild)
    click.echo(f"Thêm {r['added']}, cập nhật {r['updated']}, xóa {r['removed']}, "
               f"giữ nguyên {r['unchanged']} "
               f'(embedding: {rag.get_embedder().name})')


@bp.cli.command('stats')
@friendly_errors
def stats_cmd():
    """Thống kê kho vector và cấu hình AI hiện tại."""
    cfg = current_app.config
    llm = 'demo (không dùng LLM)' if cfg['LLM_PROVIDER'] == 'demo' \
        else f"{cfg['LLM_PROVIDER']} ({cfg['LLM_MODEL']})"
    click.echo(f'LLM      : {llm}')
    click.echo(f'Embedding: {rag.get_embedder().name}')
    click.echo(f"Top-k={cfg['AI_TOP_K']}  min_score={cfg['AI_MIN_SCORE']}  "
               f"alpha={cfg['AI_HYBRID_ALPHA']}")
    for model, source, count in rag.get_store().stats():
        click.echo(f'  {model:30} {source:8} {count:5} đoạn')


@bp.cli.command('ask')
@click.argument('question')
@click.option('--stream', is_flag=True, help='In câu trả lời dạng stream')
@friendly_errors
def ask_cmd(question, stream):
    """Hỏi trợ lý ngay trong terminal."""
    with current_app.test_request_context():  # để url_for() chạy được
        if stream:
            result = _ask_stream(question)
        else:
            result = rag.answer(question)
            click.echo(result['answer'])
    if result['blocked']:
        click.echo(f"  (Đã loại {result['blocked']} đoạn ngữ cảnh "
                   'nghi chứa prompt injection)')
    for c in result['citations']:
        click.echo(f"  [{c['n']}] {c['label']}  (điểm {c['score']})  {c['url']}")


def _ask_stream(question: str) -> dict:
    """Như rag.answer() nhưng in từng mẩu chữ ngay khi LLM gửi về."""
    if looks_like_injection(question):
        click.echo(rag.REFUSE_INJECTION)
        return {'citations': [], 'blocked': 0}
    messages, citations, blocked = rag.prepare(question)
    if not citations:
        click.echo(prompts.NO_ANSWER)
    else:
        parts = []
        for piece in LLMClient.from_config().chat(messages, stream=True):
            parts.append(piece)
            click.echo(piece, nl=False)
        click.echo()
        if prompts.NO_ANSWER in ''.join(parts):  # LLM từ chối -> không in nguồn
            citations = []
    return {'citations': citations, 'blocked': blocked}


@bp.cli.command('describe')
@click.argument('name')
@click.option('--category', default='', help='Danh mục')
@click.option('--features', default='', help='Đặc điểm, cách nhau bởi dấu phẩy')
@friendly_errors
def describe_cmd(name, category, features):
    """Viết NHÁP mô tả sản phẩm bằng LLM (hãy đọc lại trước khi đăng)."""
    click.echo(writing.describe_product(name, category, features))
