import sqlalchemy as sa
from flask import jsonify, request

from app import db
from app.api import bp
from app.models import Product


def serialize(p):
    return {
        'id': p.id, 'name': p.name, 'description': p.description,
        'price': p.price, 'stock': p.stock, 'in_stock': p.in_stock,
        'category': p.category.name if p.category else None,
        'image': p.image_url,
    }


@bp.get('/products')
def products():
    """GET /api/products?q=&page=&per_page=  → JSON danh sách sản phẩm đang bán."""
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = min(max(request.args.get('per_page', 10, type=int), 1), 50)
    stmt = sa.select(Product).where(Product.is_active.is_(True)).order_by(Product.id)
    if q:
        stmt = stmt.where(Product.name.ilike(f'%{q}%'))
    pg = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    return jsonify(items=[serialize(p) for p in pg.items],
                   page=pg.page, pages=pg.pages, total=pg.total)


@bp.get('/products/<int:id>')
def product(id):
    p = db.get_or_404(Product, id)
    if not p.is_active:
        return jsonify(error='Không tìm thấy sản phẩm'), 404
    return jsonify(serialize(p))


@bp.errorhandler(404)
def not_found(e):
    return jsonify(error='Không tìm thấy'), 404
