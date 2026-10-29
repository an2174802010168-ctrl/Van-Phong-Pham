from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
import sqlalchemy.orm as so
from flask import url_for
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db, login


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    username: so.Mapped[str] = so.mapped_column(sa.String(64), unique=True, index=True)
    email: so.Mapped[str] = so.mapped_column(sa.String(120), unique=True, index=True)
    password_hash: so.Mapped[str] = so.mapped_column(sa.String(256))
    is_admin: so.Mapped[bool] = so.mapped_column(default=False)
    created_at: so.Mapped[datetime] = so.mapped_column(default=utcnow)

    orders: so.Mapped[list['Order']] = so.relationship(
        back_populates='user', order_by='Order.id.desc()')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))


class Category(db.Model):
    __tablename__ = 'categories'

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(80), unique=True)

    products: so.Mapped[list['Product']] = so.relationship(back_populates='category')

    def __repr__(self):
        return f'<Category {self.name}>'


class Product(db.Model):
    __tablename__ = 'products'

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(150), index=True)
    description: so.Mapped[str] = so.mapped_column(sa.Text, default='')
    price: so.Mapped[int]            # VND, số nguyên để tránh sai số số thực
    stock: so.Mapped[int] = so.mapped_column(default=0)
    image: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120))
    is_active: so.Mapped[bool] = so.mapped_column(default=True)
    created_at: so.Mapped[datetime] = so.mapped_column(default=utcnow)
    category_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey('categories.id'), index=True)

    category: so.Mapped[Optional[Category]] = so.relationship(back_populates='products')

    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def image_url(self):
        if self.image:
            return url_for('static', filename='uploads/' + self.image)
        return None

    def __repr__(self):
        return f'<Product {self.name}>'


ORDER_STATUSES = {
    'pending': ('Chờ xác nhận', 'warning'),
    'confirmed': ('Đã xác nhận', 'info'),
    'shipping': ('Đang giao', 'primary'),
    'delivered': ('Đã giao', 'success'),
    'cancelled': ('Đã huỷ', 'secondary'),
}


class Order(db.Model):
    __tablename__ = 'orders'

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('users.id'), index=True)
    full_name: so.Mapped[str] = so.mapped_column(sa.String(100))
    phone: so.Mapped[str] = so.mapped_column(sa.String(20))
    address: so.Mapped[str] = so.mapped_column(sa.String(255))
    note: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    payment_method: so.Mapped[str] = so.mapped_column(sa.String(20), default='cod')
    status: so.Mapped[str] = so.mapped_column(sa.String(20), default='pending', index=True)
    subtotal: so.Mapped[int] = so.mapped_column(default=0)
    shipping_fee: so.Mapped[int] = so.mapped_column(default=0)
    created_at: so.Mapped[datetime] = so.mapped_column(default=utcnow)

    user: so.Mapped[User] = so.relationship(back_populates='orders')
    items: so.Mapped[list['OrderItem']] = so.relationship(
        back_populates='order', cascade='all, delete-orphan')

    @property
    def total(self):
        return self.subtotal + self.shipping_fee

    @property
    def status_label(self):
        return ORDER_STATUSES[self.status][0]

    @property
    def status_color(self):
        return ORDER_STATUSES[self.status][1]

    def cancel(self):
        """Huỷ đơn và hoàn lại tồn kho."""
        if self.status == 'cancelled':
            return
        for item in self.items:
            if item.product_id:
                db.session.execute(
                    sa.update(Product).where(Product.id == item.product_id)
                    .values(stock=Product.stock + item.quantity))
        self.status = 'cancelled'

    def __repr__(self):
        return f'<Order #{self.id}>'


class OrderItem(db.Model):
    """Lưu 'ảnh chụp' tên + giá tại thời điểm mua, nên đổi giá sau này không ảnh hưởng đơn cũ."""
    __tablename__ = 'order_items'

    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    order_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('orders.id'), index=True)
    product_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey('products.id', ondelete='SET NULL'))
    name: so.Mapped[str] = so.mapped_column(sa.String(150))
    price: so.Mapped[int]
    quantity: so.Mapped[int]

    order: so.Mapped[Order] = so.relationship(back_populates='items')
    product: so.Mapped[Optional[Product]] = so.relationship()

    @property
    def subtotal(self):
        return self.price * self.quantity
