import pytest
from app import create_app, db
from app.models import User, Category, Product
from config import TestingConfig


@pytest.fixture
def app():
    app = create_app(TestingConfig)
    with app.app_context():
        db.create_all()
        cat = Category(name='Thời trang')
        db.session.add_all([
            cat,
            Product(name='Áo thun', price=100000, stock=5, category=cat),
            Product(name='Quần jean', price=450000, stock=10, category=cat),
            Product(name='Hết hàng', price=50000, stock=0, category=cat),
            Product(name='Đã ẩn', price=70000, stock=5, is_active=False),
        ])
        admin = User(username='admin', email='admin@test.com', is_admin=True)
        admin.set_password('admin123')
        user = User(username='an', email='an@test.com')
        user.set_password('matkhau1')
        db.session.add_all([admin, user])
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, email, password):
    return client.post('/auth/login', data={'email': email, 'password': password},
                       follow_redirects=True)


@pytest.fixture
def user_client(client):
    login(client, 'an@test.com', 'matkhau1')
    return client


@pytest.fixture
def admin_client(client):
    login(client, 'admin@test.com', 'admin123')
    return client
