import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config
from flask_mail import Mail

mail = Mail()
db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
login.login_view = 'auth.login'
login.login_message = 'Vui lòng đăng nhập để tiếp tục.'
login.login_message_category = 'warning'
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.json.ensure_ascii = False
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    from app import models  # noqa: F401  (để Flask-Migrate thấy các model)
    from app.utils import vnd, localtime, cart_count

    app.add_template_filter(vnd, 'vnd')
    app.add_template_filter(localtime, 'localtime')

    @app.context_processor
    def inject_globals():
        return dict(shop_name=app.config['SHOP_NAME'], cart_count=cart_count())

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    from app.cart import bp as cart_bp
    app.register_blueprint(cart_bp, url_prefix='/cart')
    from app.orders import bp as orders_bp
    app.register_blueprint(orders_bp)
    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    from app.cli import register_cli
    register_cli(app)

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template('errors/413.html'), 413

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    return app
