from flask import Blueprint

bp = Blueprint('cart', __name__)

from app.cart import routes  # noqa: E402,F401
