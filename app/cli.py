import click
import sqlalchemy as sa
from email_validator import validate_email, EmailNotValidError

from app import db
from app.models import User, Category, Product


SAMPLE = {
    'Thời trang': [
        ('Áo thun cotton basic', 149000, 50, 'Áo thun cotton 100%, form rộng thoải mái, thấm hút mồ hôi tốt.'),
        ('Quần jean slim fit', 399000, 30, 'Quần jean co giãn nhẹ, dáng slim fit dễ phối đồ.'),
        ('Giày sneaker trắng', 590000, 20, 'Giày sneaker da tổng hợp, đế cao su êm, dễ vệ sinh.'),
        ('Balo laptop chống nước', 359000, 25, 'Balo chống nước, ngăn đệm laptop 15.6 inch, nhiều ngăn tiện dụng.'),
    ],
    'Phụ kiện công nghệ': [
        ('Tai nghe Bluetooth 5.3', 450000, 40, 'Tai nghe không dây, pin 30 giờ, chống ồn cơ bản.'),
        ('Chuột không dây', 199000, 60, 'Chuột không dây 2.4GHz, yên tĩnh, pin dùng 12 tháng.'),
        ('Bàn phím cơ TKL', 890000, 15, 'Bàn phím cơ layout TKL, switch red, đèn nền LED.'),
        ('Sạc dự phòng 10000mAh', 290000, 3, 'Sạc dự phòng nhỏ gọn, hỗ trợ sạc nhanh 20W.'),
    ],
    'Gia dụng': [
        ('Cốc giữ nhiệt 500ml', 180000, 45, 'Cốc inox 304 giữ nóng 8 giờ, giữ lạnh 12 giờ.'),
        ('Đèn bàn LED chống cận', 250000, 18, 'Đèn bàn LED 3 chế độ sáng, điều chỉnh độ sáng, bảo vệ mắt.'),
    ],
    'Văn phòng phẩm': [
        ('Sổ tay A5 bìa cứng', 59000, 100, 'Sổ tay A5, 200 trang giấy dày, chống lem mực.'),
        ('Bút gel (hộp 10 cây)', 45000, 0, 'Bút gel mực đen 0.5mm, viết mượt. Hiện đang hết hàng.'),
    ],
}


def register_cli(app):
    @app.cli.command('seed')
    def seed():
        """Tạo bảng và nạp dữ liệu mẫu (chạy lại nhiều lần vẫn an toàn)."""
        db.create_all()
        if db.session.scalar(sa.select(sa.func.count(Product.id))):
            click.echo('Đã có sản phẩm, bỏ qua dữ liệu mẫu.')
            return
        for cat_name, items in SAMPLE.items():
            cat = Category(name=cat_name)
            db.session.add(cat)
            for name, price, stock, desc in items:
                db.session.add(Product(name=name, price=price, stock=stock,
                                       description=desc, category=cat))
        db.session.commit()
        click.echo('Đã nạp danh mục và sản phẩm mẫu. Tạo tài khoản admin: flask create-admin')

    @app.cli.command('create-admin')
    @click.option('--email', prompt=True)
    @click.option('--username', prompt=True)
    @click.password_option()
    def create_admin(email, username, password):
        """Tạo (hoặc nâng quyền) tài khoản quản trị."""
        try:  # dùng đúng bộ kiểm tra của form đăng nhập, tránh tạo tài khoản không đăng nhập được
            validate_email(email, check_deliverability=False)
        except EmailNotValidError as e:
            raise click.BadParameter(f'{e} (gợi ý: dùng vd. admin@example.com, tránh đuôi .local)',
                                     param_hint='--email')
        db.create_all()
        user = db.session.scalar(sa.select(User).where(User.email == email.lower()))
        if user is None:
            user = User(email=email.lower(), username=username)
            db.session.add(user)
        user.set_password(password)
        user.is_admin = True
        db.session.commit()
        click.echo(f'Đã tạo/cập nhật admin: {user.email}')
