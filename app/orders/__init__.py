from flask import Blueprint

bp = Blueprint('orders', __name__)

from app.orders import routes  # noqa: E402,F401
