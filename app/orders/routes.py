import sqlalchemy as sa
from flask import render_template, redirect, url_for, flash, session, abort, request, current_app
from flask_login import login_required, current_user

from app import db
from app.models import Order, OrderItem, Product
from app.orders import bp
from app.orders.forms import CheckoutForm
from app.utils import cart_lines, shipping_fee
from app.email import send_order_confirmation


@bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    lines, subtotal = cart_lines()
    if not lines:
        flash('Giỏ hàng của bạn đang trống.', 'warning')
        return redirect(url_for('cart.view'))
    fee = shipping_fee(subtotal)

    form = CheckoutForm()
    if request.method == 'GET':
        last = db.session.scalar(
            sa.select(Order).where(Order.user_id == current_user.id).order_by(Order.id.desc()))
        form.full_name.data = last.full_name if last else current_user.username
        if last:
            form.phone.data, form.address.data = last.phone, last.address

    if form.validate_on_submit():
        order = Order(user=current_user, full_name=form.full_name.data.strip(),
                      phone=form.phone.data.strip(), address=form.address.data.strip(),
                      note=(form.note.data or '').strip() or None,
                      subtotal=subtotal, shipping_fee=fee)
        db.session.add(order)
        for line in lines:
            # Trừ kho nguyên tử: chỉ thành công khi còn đủ hàng → không bán lố khi nhiều người đặt cùng lúc
            result = db.session.execute(
                sa.update(Product)
                .where(Product.id == line.product.id, Product.stock >= line.quantity)
                .values(stock=Product.stock - line.quantity))
            if result.rowcount != 1:
                db.session.rollback()
                flash(f'"{line.product.name}" không còn đủ hàng. Vui lòng kiểm tra lại giỏ.', 'danger')
                return redirect(url_for('cart.view'))
            order.items.append(OrderItem(product_id=line.product.id, name=line.product.name,
                                         price=line.product.price, quantity=line.quantity))
        db.session.commit()
        session.pop('cart', None)
        send_order_confirmation(order)
        flash(f'Đặt hàng thành công! Mã đơn của bạn là #{order.id}.', 'success')
        return redirect(url_for('orders.detail', id=order.id))

    return render_template('orders/checkout.html', form=form, lines=lines,
                           subtotal=subtotal, fee=fee, total=subtotal + fee)


@bp.route('/orders')
@login_required
def history():
    page = request.args.get('page', 1, type=int)
    stmt = sa.select(Order).where(Order.user_id == current_user.id).order_by(Order.id.desc())
    pagination = db.paginate(stmt, page=page, per_page=current_app.config['ADMIN_PER_PAGE'],
                             error_out=False)
    return render_template('orders/history.html', pagination=pagination, orders=pagination.items)


@bp.route('/orders/<int:id>')
@login_required
def detail(id):
    order = db.get_or_404(Order, id)
    if order.user_id != current_user.id and not current_user.is_admin:
        abort(404)
    return render_template('orders/detail.html', order=order)


@bp.post('/orders/<int:id>/cancel')
@login_required
def cancel(id):
    order = db.get_or_404(Order, id)
    if order.user_id != current_user.id:
        abort(404)
    if order.status != 'pending':
        flash('Chỉ có thể huỷ đơn đang chờ xác nhận.', 'warning')
    else:
        order.cancel()
        db.session.commit()
        flash(f'Đã huỷ đơn #{order.id}.', 'info')
    return redirect(url_for('orders.detail', id=order.id))