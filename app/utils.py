import os
import uuid
from dataclasses import dataclass
from datetime import timezone, timedelta
from functools import wraps
from urllib.parse import urlsplit

from flask import session, current_app, abort
from flask_login import current_user
from werkzeug.utils import secure_filename

from app import db
from app.models import Product

VN_TZ = timezone(timedelta(hours=7))  # Việt Nam không dùng giờ mùa hè


# ---------- Bộ lọc Jinja ----------
def vnd(value):
    """1234567 -> '1.234.567 ₫'"""
    return f'{int(value or 0):,}'.replace(',', '.') + ' ₫'


def localtime(dt, fmt='%d/%m/%Y %H:%M'):
    if dt is None:
        return ''
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(VN_TZ).strftime(fmt)


# ---------- Giỏ hàng (lưu trong session, khách chưa đăng nhập vẫn dùng được) ----------
@dataclass
class CartLine:
    product: Product
    quantity: int

    @property
    def subtotal(self):
        return self.product.price * self.quantity


def cart_count():
    return sum((session.get('cart') or {}).values())


def cart_lines():
    """Trả về (danh sách CartLine, tạm tính). Tự dọn sản phẩm đã ẩn/hết hàng
    và cắt số lượng về mức tồn kho hiện có."""
    cart = session.get('cart') or {}
    lines, changed = [], False
    for pid, qty in list(cart.items()):
        product = db.session.get(Product, int(pid))
        if product is None or not product.is_active or product.stock <= 0:
            cart.pop(pid)
            changed = True
            continue
        if qty > product.stock:
            qty = cart[pid] = product.stock
            changed = True
        lines.append(CartLine(product, qty))
    if changed:
        session['cart'] = cart
    return lines, sum(line.subtotal for line in lines)


def shipping_fee(subtotal):
    cfg = current_app.config
    if subtotal <= 0 or subtotal >= cfg['FREE_SHIPPING_FROM']:
        return 0
    return cfg['SHIPPING_FEE']


# ---------- Tiện ích khác ----------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not (current_user.is_authenticated and current_user.is_admin):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def is_safe_url(target):
    """Chỉ cho redirect tới đường dẫn nội bộ (chống open redirect)."""
    if not target:
        return False
    parts = urlsplit(target)
    return not parts.netloc and not parts.scheme and target.startswith('/') \
        and not target.startswith('//')


def save_image(file_storage):
    ext = os.path.splitext(secure_filename(file_storage.filename))[1].lower()
    name = f'{uuid.uuid4().hex}{ext}'
    file_storage.save(os.path.join(current_app.config['UPLOAD_FOLDER'], name))
    return name


def delete_image(name):
    if name:
        try:
            os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], name))
        except OSError:
            pass
