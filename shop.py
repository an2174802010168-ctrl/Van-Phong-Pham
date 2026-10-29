from app import create_app, db
from app.models import User, Category, Product, Order, OrderItem

app = create_app()


@app.shell_context_processor
def make_shell_context():
    return dict(db=db, User=User, Category=Category, Product=Product,
                Order=Order, OrderItem=OrderItem)
