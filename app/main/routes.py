import sqlalchemy as sa
from flask import render_template, request, current_app, abort
from flask_login import current_user

from app import db
from app.main import bp
from app.models import Product, Category
from app.services import get_usd_rate
SORTS = {
    'new': (Product.id.desc(), 'Mới nhất'),
    'price_asc': (Product.price.asc(), 'Giá tăng dần'),
    'price_desc': (Product.price.desc(), 'Giá giảm dần'),
    'name': (Product.name.asc(), 'Tên A → Z'),
}


@bp.route('/')
def index():
    q = request.args.get('q', '').strip()
    category_id = request.args.get('category', type=int)
    sort = request.args.get('sort', 'new')
    if sort not in SORTS:
        sort = 'new'

    stmt = sa.select(Product).where(Product.is_active.is_(True))
    if q:
        stmt = stmt.where(Product.name.ilike(f'%{q}%'))
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    stmt = stmt.order_by(SORTS[sort][0])

    page = request.args.get('page', 1, type=int)
    pagination = db.paginate(stmt, page=page, error_out=False,
                             per_page=current_app.config['PRODUCTS_PER_PAGE'])
    categories = db.session.scalars(sa.select(Category).order_by(Category.name)).all()
    return render_template('index.html', pagination=pagination, products=pagination.items,
                           categories=categories, q=q, category_id=category_id,
                           sort=sort, sorts=SORTS)


@bp.route('/product/<int:id>')
def product(id):
    product = db.get_or_404(Product, id)
    if not product.is_active and not (current_user.is_authenticated and current_user.is_admin):
        abort(404)
    related = []
    if product.category_id:
        related = db.session.scalars(
            sa.select(Product)
            .where(Product.category_id == product.category_id,
                   Product.id != product.id, Product.is_active.is_(True))
            .order_by(Product.id.desc()).limit(4)).all()
    return render_template('product.html', product=product, related=related,
                           usd_rate=get_usd_rate())
