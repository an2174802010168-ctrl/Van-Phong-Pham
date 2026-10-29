from flask import render_template, redirect, url_for, flash, request, session, abort

from app import db
from app.cart import bp
from app.models import Product
from app.utils import cart_lines, shipping_fee, is_safe_url


def _back(default):
    nxt = request.form.get('next')
    return redirect(nxt if is_safe_url(nxt) else default)


@bp.route('/')
def view():
    lines, subtotal = cart_lines()
    fee = shipping_fee(subtotal)
    return render_template('cart.html', lines=lines, subtotal=subtotal,
                           fee=fee, total=subtotal + fee)


@bp.post('/add/<int:product_id>')
def add(product_id):
    product = db.get_or_404(Product, product_id)
    if not product.is_active:
        abort(404)
    if product.stock <= 0:
        flash('Sản phẩm này đã hết hàng.', 'warning')
        return _back(url_for('main.product', id=product.id))

    qty = max(1, request.form.get('quantity', 1, type=int))
    cart = session.get('cart') or {}
    key = str(product.id)
    new_qty = cart.get(key, 0) + qty
    if new_qty > product.stock:
        new_qty = product.stock
        flash(f'Chỉ còn {product.stock} sản phẩm "{product.name}" trong kho.', 'warning')
    else:
        flash(f'Đã thêm "{product.name}" vào giỏ hàng.', 'success')
    cart[key] = new_qty
    session['cart'] = cart
    return _back(url_for('cart.view'))


@bp.post('/update/<int:product_id>')
def update(product_id):
    product = db.get_or_404(Product, product_id)
    qty = request.form.get('quantity', 1, type=int)
    cart = session.get('cart') or {}
    key = str(product_id)
    if key in cart:
        if qty <= 0:
            cart.pop(key)
        else:
            if qty > product.stock:
                qty = product.stock
                flash(f'Chỉ còn {product.stock} sản phẩm trong kho.', 'warning')
            cart[key] = qty
        session['cart'] = cart
    return redirect(url_for('cart.view'))


@bp.post('/remove/<int:product_id>')
def remove(product_id):
    cart = session.get('cart') or {}
    if cart.pop(str(product_id), None) is not None:
        session['cart'] = cart
        flash('Đã xoá sản phẩm khỏi giỏ hàng.', 'info')
    return redirect(url_for('cart.view'))
