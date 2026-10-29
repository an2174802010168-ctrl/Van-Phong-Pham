import sqlalchemy as sa

from app import db
from app.models import Product, Order, User
from app.utils import vnd
from tests.conftest import login


def pid(name):
    return db.session.scalar(sa.select(Product.id).where(Product.name == name))


SHIP = dict(full_name='Nguyễn An', phone='0901234567', address='1 Lê Lợi, Q1, TP.HCM')


# ---------- Cửa hàng ----------
def test_vnd_filter():
    assert vnd(1234567) == '1.234.567 ₫'
    assert vnd(0) == '0 ₫'


def test_catalog_hides_inactive_and_supports_search(client):
    html = client.get('/').get_data(as_text=True)
    assert 'Áo thun' in html and 'Đã ẩn' not in html
    html = client.get('/?q=jean').get_data(as_text=True)
    assert 'Quần jean' in html and 'Áo thun' not in html


def test_sort_by_price_desc(client):
    html = client.get('/?sort=price_desc').get_data(as_text=True)
    assert html.index('Quần jean') < html.index('Áo thun')


def test_inactive_product_404_for_public(client, app):
    assert client.get(f'/product/{pid("Đã ẩn")}').status_code == 404
    assert client.get('/product/9999').status_code == 404


# ---------- Tài khoản ----------
def test_register_login_logout(client):
    r = client.post('/auth/register', data=dict(
        username='binh', email='Binh@Test.com', password='abcdef', password2='abcdef'),
        follow_redirects=True)
    assert 'Đăng ký thành công' in r.get_data(as_text=True)
    assert db.session.scalar(sa.select(User).where(User.email == 'binh@test.com'))  # email chuẩn hoá chữ thường
    client.post('/auth/logout')
    assert 'Đăng nhập' in client.get('/').get_data(as_text=True)


def test_register_rejects_duplicate_email_and_weak_password(client):
    r = client.post('/auth/register', data=dict(
        username='x', email='an@test.com', password='123', password2='123'))
    html = r.get_data(as_text=True)
    assert 'đã được đăng ký' in html and 'ít nhất 6' in html or 'at least 6' in html


def test_wrong_password(client):
    r = login(client, 'an@test.com', 'sai')
    assert 'không đúng' in r.get_data(as_text=True)


def test_login_blocks_open_redirect(client):
    r = client.post('/auth/login?next=https://evil.com',
                    data={'email': 'an@test.com', 'password': 'matkhau1'})
    assert r.status_code == 302 and 'evil.com' not in r.headers['Location']


# ---------- Giỏ hàng ----------
def test_cart_add_clamps_to_stock(client):
    i = pid('Áo thun')
    client.post(f'/cart/add/{i}', data={'quantity': 99})
    html = client.get('/cart/').get_data(as_text=True)
    assert 'Áo thun' in html and 'value="5"' in html  # kho chỉ có 5


def test_cart_rejects_out_of_stock_and_hidden(client):
    client.post(f'/cart/add/{pid("Hết hàng")}')
    assert client.post(f'/cart/add/{pid("Đã ẩn")}').status_code == 404
    assert 'trống' in client.get('/cart/').get_data(as_text=True)


def test_cart_update_and_remove(client):
    i = pid('Áo thun')
    client.post(f'/cart/add/{i}')
    client.post(f'/cart/update/{i}', data={'quantity': 3})
    with client.session_transaction() as s:
        assert s['cart'] == {str(i): 3}
    client.post(f'/cart/remove/{i}')
    with client.session_transaction() as s:
        assert s['cart'] == {}


# ---------- Đặt hàng ----------
def test_checkout_requires_login(client):
    r = client.get('/checkout')
    assert r.status_code == 302 and '/auth/login' in r.headers['Location']


def test_checkout_creates_order_decrements_stock_and_charges_shipping(user_client):
    i = pid('Áo thun')
    user_client.post(f'/cart/add/{i}', data={'quantity': 2})   # 200.000 < 500.000 → có phí ship
    r = user_client.post('/checkout', data=SHIP, follow_redirects=True)
    assert 'Đặt hàng thành công' in r.get_data(as_text=True)
    order = db.session.scalar(sa.select(Order))
    assert order.subtotal == 200000 and order.shipping_fee == 30000 and order.total == 230000
    assert order.items[0].quantity == 2
    assert db.session.get(Product, i).stock == 3
    with user_client.session_transaction() as s:
        assert 'cart' not in s


def test_free_shipping_over_threshold(user_client):
    user_client.post(f'/cart/add/{pid("Quần jean")}', data={'quantity': 2})  # 900.000
    user_client.post('/checkout', data=SHIP)
    assert db.session.scalar(sa.select(Order)).shipping_fee == 0


def test_checkout_validates_phone(user_client):
    user_client.post(f'/cart/add/{pid("Áo thun")}')
    r = user_client.post('/checkout', data={**SHIP, 'phone': 'abc'})
    assert 'không hợp lệ' in r.get_data(as_text=True)
    assert db.session.scalar(sa.select(Order)) is None


def test_cart_is_clamped_when_stock_drops(user_client):
    i = pid('Áo thun')
    user_client.post(f'/cart/add/{i}', data={'quantity': 5})
    db.session.get(Product, i).stock = 1
    db.session.commit()
    user_client.post('/checkout', data=SHIP)
    assert db.session.scalar(sa.select(Order)).items[0].quantity == 1   # tự cắt về tồn kho
    assert db.session.get(Product, i).stock == 0


def test_checkout_atomic_stock_guard_blocks_overselling(user_client, monkeypatch):
    """Giả lập: người khác mua hết hàng NGAY SAU khi giỏ được tính, trước khi trừ kho."""
    import app.orders.routes as routes
    i = pid('Áo thun')
    user_client.post(f'/cart/add/{i}', data={'quantity': 3})
    real = routes.cart_lines

    def stale_cart_lines():
        result = real()
        db.session.execute(sa.update(Product).where(Product.id == i).values(stock=1))
        db.session.commit()
        return result
    monkeypatch.setattr(routes, 'cart_lines', stale_cart_lines)

    r = user_client.post('/checkout', data=SHIP, follow_redirects=True)
    assert 'không còn đủ hàng' in r.get_data(as_text=True)
    assert db.session.scalar(sa.select(Order)) is None
    assert db.session.get(Product, i).stock == 1


def test_price_snapshot_survives_price_change(user_client):
    i = pid('Áo thun')
    user_client.post(f'/cart/add/{i}')
    user_client.post('/checkout', data=SHIP)
    db.session.get(Product, i).price = 999999
    db.session.commit()
    assert db.session.scalar(sa.select(Order)).items[0].price == 100000


def test_user_can_cancel_pending_order_and_stock_returns(user_client):
    i = pid('Áo thun')
    user_client.post(f'/cart/add/{i}', data={'quantity': 2})
    user_client.post('/checkout', data=SHIP)
    oid = db.session.scalar(sa.select(Order.id))
    user_client.post(f'/orders/{oid}/cancel')
    assert db.session.get(Order, oid).status == 'cancelled'
    assert db.session.get(Product, i).stock == 5


def test_user_cannot_view_others_order(app, client):
    u2 = User(username='c', email='c@test.com'); u2.set_password('abcdef')
    db.session.add(u2); db.session.commit()
    login(client, 'an@test.com', 'matkhau1')
    client.post(f'/cart/add/{pid("Áo thun")}')
    client.post('/checkout', data=SHIP)
    oid = db.session.scalar(sa.select(Order.id))
    client.post('/auth/logout')
    login(client, 'c@test.com', 'abcdef')
    assert client.get(f'/orders/{oid}').status_code == 404


# ---------- Quản trị ----------
def test_admin_area_protected(client, user_client):
    assert user_client.get('/admin/').status_code == 403
    assert user_client.get('/admin/products').status_code == 403


def test_admin_anonymous_redirected_to_login(client):
    r = client.get('/admin/')
    assert r.status_code == 302 and '/auth/login' in r.headers['Location']


def test_admin_pages_render(admin_client):
    for url in ['/admin/', '/admin/products', '/admin/products/new',
                '/admin/categories', '/admin/orders']:
        assert admin_client.get(url).status_code == 200, url


def test_admin_product_crud(admin_client):
    r = admin_client.post('/admin/products/new', data=dict(
        name='Mũ lưỡi trai', category=1, price=80000, stock=7, description='đẹp', is_active='y'),
        follow_redirects=True)
    assert 'Đã thêm sản phẩm' in r.get_data(as_text=True)
    i = pid('Mũ lưỡi trai')
    admin_client.post(f'/admin/products/{i}/edit', data=dict(
        name='Mũ lưỡi trai', category=1, price=90000, stock=7, description='đẹp', is_active='y'))
    assert db.session.get(Product, i).price == 90000
    admin_client.post(f'/admin/products/{i}/delete')
    assert db.session.get(Product, i) is None


def test_admin_delete_sold_product_only_hides_it(admin_client, app):
    i = pid('Áo thun')
    admin_client.post(f'/cart/add/{i}')
    admin_client.post('/checkout', data=SHIP)
    admin_client.post(f'/admin/products/{i}/delete')
    p = db.session.get(Product, i)
    assert p is not None and p.is_active is False


def test_admin_updates_status_and_cancel_restores_stock(admin_client):
    i = pid('Áo thun')
    admin_client.post(f'/cart/add/{i}', data={'quantity': 2})
    admin_client.post('/checkout', data=SHIP)
    oid = db.session.scalar(sa.select(Order.id))
    admin_client.post(f'/admin/orders/{oid}', data={'status': 'shipping'})
    assert db.session.get(Order, oid).status == 'shipping'
    admin_client.post(f'/admin/orders/{oid}', data={'status': 'cancelled'})
    assert db.session.get(Order, oid).status == 'cancelled'
    assert db.session.get(Product, i).stock == 5
    admin_client.post(f'/admin/orders/{oid}', data={'status': 'delivered'})   # đơn huỷ: không đổi được
    assert db.session.get(Order, oid).status == 'cancelled'


def test_category_cannot_delete_if_has_products(admin_client):
    admin_client.post('/admin/categories/1/delete')
    r = admin_client.get('/admin/categories')
    assert 'Thời trang' in r.get_data(as_text=True)


# ---------- CLI ----------
def test_create_admin_rejects_unloginable_email_and_creates_valid_one(app):
    runner = app.test_cli_runner()
    bad = runner.invoke(args=['create-admin', '--email', 'a@shop.local', '--username', 'x',
                              '--password', 'abcdef'])
    assert bad.exit_code != 0
    ok = runner.invoke(args=['create-admin', '--email', 'Boss@Example.com', '--username', 'boss',
                             '--password', 'abcdef'])
    assert ok.exit_code == 0
    u = db.session.scalar(sa.select(User).where(User.email == 'boss@example.com'))
    assert u.is_admin and u.check_password('abcdef')
