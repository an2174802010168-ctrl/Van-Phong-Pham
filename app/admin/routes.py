import sqlalchemy as sa
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required

from app import db
from app.admin import bp
from app.admin.forms import ProductForm, CategoryForm, OrderStatusForm
from app.models import Product, Category, Order, OrderItem, User, ORDER_STATUSES
from app.utils import admin_required, save_image, delete_image
from werkzeug.datastructures import FileStorage

@bp.before_request
@login_required
@admin_required
def guard():
    """Mọi route trong /admin yêu cầu đăng nhập + quyền quản trị."""


# ---------- Tổng quan ----------
@bp.route('/')
def dashboard():
    scalar = db.session.scalar
    stats = dict(
        products=scalar(sa.select(sa.func.count(Product.id))),
        users=scalar(sa.select(sa.func.count(User.id))),
        orders=scalar(sa.select(sa.func.count(Order.id))),
        pending=scalar(sa.select(sa.func.count(Order.id)).where(Order.status == 'pending')),
        revenue=scalar(sa.select(sa.func.coalesce(
            sa.func.sum(Order.subtotal + Order.shipping_fee), 0))
            .where(Order.status != 'cancelled')),
    )
    recent = db.session.scalars(sa.select(Order).order_by(Order.id.desc()).limit(5)).all()
    low_stock = db.session.scalars(
        sa.select(Product).where(Product.is_active.is_(True), Product.stock <= 5)
        .order_by(Product.stock).limit(8)).all()
    return render_template('admin/dashboard.html', stats=stats, recent=recent, low_stock=low_stock)


# ---------- Sản phẩm ----------
@bp.route('/products')
def products():
    q = request.args.get('q', '').strip()
    stmt = sa.select(Product).order_by(Product.id.desc())
    if q:
        stmt = stmt.where(Product.name.ilike(f'%{q}%'))
    page = request.args.get('page', 1, type=int)
    pagination = db.paginate(stmt, page=page, error_out=False,
                             per_page=current_app.config['ADMIN_PER_PAGE'])
    return render_template('admin/products.html', pagination=pagination,
                           products=pagination.items, q=q)


def _category_choices(form):
    cats = db.session.scalars(sa.select(Category).order_by(Category.name)).all()
    form.category.choices = [(0, '— Chưa phân loại —')] + [(c.id, c.name) for c in cats]


@bp.route('/products/new', methods=['GET', 'POST'])
def product_new():
    form = ProductForm()
    _category_choices(form)
    if form.validate_on_submit():
        product = Product(name=form.name.data.strip(), price=form.price.data,
                          stock=form.stock.data or 0, description=form.description.data or '',
                          category_id=form.category.data or None, is_active=form.is_active.data)
        if isinstance(form.image.data, FileStorage) and form.image.data.filename:
            product.image = save_image(form.image.data)
        db.session.add(product)
        db.session.commit()
        flash(f'Đã thêm sản phẩm "{product.name}".', 'success')
        return redirect(url_for('admin.products'))
    return render_template('admin/product_form.html', form=form, title='Thêm sản phẩm', product=None)


@bp.route('/products/<int:id>/edit', methods=['GET', 'POST'])
def product_edit(id):
    product = db.get_or_404(Product, id)
    form = ProductForm(obj=product)
    _category_choices(form)
    if request.method == 'GET':
        form.category.data = product.category_id or 0
    if form.validate_on_submit():
        product.name = form.name.data.strip()
        product.price = form.price.data
        product.stock = form.stock.data or 0
        product.description = form.description.data or ''
        product.category_id = form.category.data or None
        product.is_active = form.is_active.data
        if isinstance(form.image.data, FileStorage) and form.image.data.filename:
            delete_image(product.image)
            product.image = save_image(form.image.data)
        db.session.commit()
        flash('Đã cập nhật sản phẩm.', 'success')
        return redirect(url_for('admin.products'))
    return render_template('admin/product_form.html', form=form, title='Sửa sản phẩm', product=product)


@bp.post('/products/<int:id>/delete')
def product_delete(id):
    product = db.get_or_404(Product, id)
    sold = db.session.scalar(sa.select(sa.func.count(OrderItem.id))
                             .where(OrderItem.product_id == product.id))
    if sold:
        # Đã có người mua → giữ lại để không mất lịch sử đơn, chỉ ẩn khỏi cửa hàng
        product.is_active = False
        flash(f'"{product.name}" đã có trong đơn hàng nên được ẩn đi thay vì xoá.', 'info')
    else:
        delete_image(product.image)
        db.session.delete(product)
        flash(f'Đã xoá sản phẩm "{product.name}".', 'success')
    db.session.commit()
    return redirect(url_for('admin.products'))


# ---------- Danh mục ----------
@bp.route('/categories', methods=['GET', 'POST'])
def categories():
    form = CategoryForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        if db.session.scalar(sa.select(Category).where(sa.func.lower(Category.name) == name.lower())):
            flash('Danh mục này đã tồn tại.', 'warning')
        else:
            db.session.add(Category(name=name))
            db.session.commit()
            flash(f'Đã thêm danh mục "{name}".', 'success')
        return redirect(url_for('admin.categories'))
    rows = db.session.execute(
        sa.select(Category, sa.func.count(Product.id))
        .outerjoin(Product, Product.category_id == Category.id)
        .group_by(Category.id).order_by(Category.name)).all()
    return render_template('admin/categories.html', form=form, rows=rows)


@bp.post('/categories/<int:id>/delete')
def category_delete(id):
    category = db.get_or_404(Category, id)
    if category.products:
        flash('Danh mục còn sản phẩm, hãy chuyển sản phẩm sang danh mục khác trước.', 'warning')
    else:
        db.session.delete(category)
        db.session.commit()
        flash('Đã xoá danh mục.', 'success')
    return redirect(url_for('admin.categories'))


# ---------- Đơn hàng ----------
@bp.route('/orders')
def orders():
    status = request.args.get('status', '')
    stmt = sa.select(Order).order_by(Order.id.desc())
    if status in ORDER_STATUSES:
        stmt = stmt.where(Order.status == status)
    page = request.args.get('page', 1, type=int)
    pagination = db.paginate(stmt, page=page, error_out=False,
                             per_page=current_app.config['ADMIN_PER_PAGE'])
    return render_template('admin/orders.html', pagination=pagination, orders=pagination.items,
                           status=status, statuses=ORDER_STATUSES)


@bp.route('/orders/<int:id>', methods=['GET', 'POST'])
def order_detail(id):
    order = db.get_or_404(Order, id)
    form = OrderStatusForm(status=order.status)
    if form.validate_on_submit():
        new = form.status.data
        if order.status == 'cancelled':
            flash('Đơn đã huỷ không thể thay đổi trạng thái.', 'warning')
        elif new == 'cancelled':
            order.cancel()          # hoàn lại tồn kho
            db.session.commit()
            flash('Đã huỷ đơn và hoàn lại tồn kho.', 'info')
        else:
            order.status = new
            db.session.commit()
            flash('Đã cập nhật trạng thái đơn hàng.', 'success')
        return redirect(url_for('admin.order_detail', id=order.id))
    return render_template('admin/order_detail.html', order=order, form=form)
