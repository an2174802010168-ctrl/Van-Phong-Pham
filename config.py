import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))
RATE_API_URL = os.environ.get('RATE_API_URL') or 'https://open.er-api.com/v6/latest/USD'

class Config:
    SHOP_NAME = 'Văn Phòng Phẩm'
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-hay-doi-khi-trien-khai'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')

    PRODUCTS_PER_PAGE = 8
    ADMIN_PER_PAGE = 15

    # Phí vận chuyển (VND): miễn phí cho đơn từ FREE_SHIPPING_FROM
    SHIPPING_FEE = 30000
    FREE_SHIPPING_FROM = 500000

    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('1', 'true', 'yes')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or MAIL_USERNAME

    # Upload ảnh sản phẩm
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = 'test'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'   # SQLite trong bộ nhớ
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    MAIL_DEFAULT_SENDER = 'shop@test.com'