from flask import current_app
from flask_mail import Message

from app import mail
from app.utils import vnd


def send_order_confirmation(order):
    """Gửi email xác nhận đơn hàng. Lỗi gửi mail không được làm hỏng việc đặt hàng."""
    cfg = current_app.config
    if not cfg.get('MAIL_USERNAME') and not cfg.get('TESTING'):
        return False                      # chưa cấu hình SMTP → bỏ qua
    shop = cfg['SHOP_NAME']
    lines = [f'Chào {order.full_name},', '',
             f'Cảm ơn bạn đã đặt hàng tại {shop}. Mã đơn của bạn là #{order.id}.', '']
    for item in order.items:
        lines.append(f'- {item.name} x {item.quantity}: {vnd(item.subtotal)}')
    lines += ['', f'Tạm tính: {vnd(order.subtotal)}',
              f'Phí vận chuyển: {vnd(order.shipping_fee)}',
              f'Tổng cộng: {vnd(order.total)}', '',
              f'Giao tới: {order.address} ({order.phone})',
              'Thanh toán khi nhận hàng (COD).']
    msg = Message(subject=f'[{shop}] Xác nhận đơn hàng #{order.id}',
                  recipients=[order.user.email], body='\n'.join(lines))
    try:
        mail.send(msg)
        return True
    except Exception:
        current_app.logger.exception('Không gửi được email xác nhận đơn #%s', order.id)
        return False
