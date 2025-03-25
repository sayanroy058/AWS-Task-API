from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import requests

app = Flask(__name__)

# Configuration
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'ecommerce.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_PATH}'
app.config['SECRET_KEY'] = 'your-secret-key-here'

db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    cart_items = db.relationship('CartItem', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.String(100), primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100))
    description = db.Column(db.Text)
    price = db.Column(db.Float)
    rentprice = db.Column(db.Float)
    size = db.Column(db.String(50))
    image = db.Column(db.String(255))
    rating_rate = db.Column(db.Float)
    rating_count = db.Column(db.Integer)

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.String(100), db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    product = db.relationship('Product')

# Authentication Routes
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already exists'}), 400
    
    user = User(username=data['username'], email=data['email'])
    user.set_password(data['password'])
    
    db.session.add(user)
    db.session.commit()
    
    return jsonify({'message': 'User registered successfully'}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(username=data['username']).first()
    
    if user and user.check_password(data['password']):
        return jsonify({
            'message': 'Login successful',
            'user_id': user.id,
            'username': user.username
        })
    
    return jsonify({'error': 'Invalid username or password'}), 401

# Cart Routes
@app.route('/api/cart', methods=['GET'])
def get_cart():
    user_id = request.args.get('user_id')
    cart_items = CartItem.query.filter_by(user_id=user_id).all()
    
    items = [{
        'id': item.id,
        'product': {
            'id': item.product.id,
            'title': item.product.title,
            'price': item.product.price,
            'image': item.product.image
        },
        'quantity': item.quantity,
        'added_at': item.added_at.isoformat()
    } for item in cart_items]
    
    return jsonify({'cart_items': items})

@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    data = request.get_json()
    user_id = data['user_id']
    product_id = data['product_id']
    quantity = data.get('quantity', 1)
    
    existing_item = CartItem.query.filter_by(
        user_id=user_id,
        product_id=product_id
    ).first()
    
    if existing_item:
        existing_item.quantity += quantity
    else:
        cart_item = CartItem(
            user_id=user_id,
            product_id=product_id,
            quantity=quantity
        )
        db.session.add(cart_item)
    
    db.session.commit()
    return jsonify({'message': 'Item added to cart successfully'})

@app.route('/api/cart/update', methods=['PUT'])
def update_cart_item():
    data = request.get_json()
    cart_item = CartItem.query.get(data['cart_item_id'])
    
    if not cart_item:
        return jsonify({'error': 'Cart item not found'}), 404
    
    cart_item.quantity = data['quantity']
    db.session.commit()
    
    return jsonify({'message': 'Cart item updated successfully'})

@app.route('/api/cart/remove', methods=['DELETE'])
def remove_from_cart():
    cart_item_id = request.args.get('cart_item_id')
    cart_item = CartItem.query.get(cart_item_id)
    
    if not cart_item:
        return jsonify({'error': 'Cart item not found'}), 404
    
    db.session.delete(cart_item)
    db.session.commit()
    
    return jsonify({'message': 'Item removed from cart successfully'})

# Product Routes
@app.route('/products', methods=['GET'])
def get_products():
    search = request.args.get('search')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 5))

    query = Product.query
    if search:
        query = query.filter(Product.title.contains(search))

    products = query.paginate(page=page, per_page=per_page, error_out=False)

    result = [{
        'id': product.id,
        'title': product.title,
        'category': product.category,
        'description': product.description,
        'price': product.price,
        'rentprice': product.rentprice,
        'size': product.size,
        'image': product.image,
        'rating': {
            'rate': product.rating_rate,
            'count': product.rating_count
        }
    } for product in products.items]

    return jsonify({
        'products': result,
        'total': products.total,
        'pages': products.pages,
        'current_page': products.page
    })

# Fetch Products from External API
@app.route('/fetch-products', methods=['GET'])
def fetch_products():
    url = 'http://3.250.87.6:3000/freelancer/products'
    response = requests.get(url)
    if response.status_code != 200:
        return jsonify({'error': 'Failed to fetch products'}), 500
    
    products = response.json()

    for product in products:
        new_product = Product(
            id=product['_id'],
            title=product['title'],
            category=product['category'],
            description=product['description'],
            price=product['price'],
            rentprice=product['rentprice'],
            size=product['size'],
            image=product['image'],
            rating_rate=product['rating']['rate'],
            rating_count=product['rating']['count']
        )
        db.session.merge(new_product)
    
    db.session.commit()
    return jsonify({'message': 'Products fetched and stored successfully'}), 201

# Create database
def create_database():
    if not os.path.exists(DATABASE_PATH):
        with app.app_context():
            db.create_all()
            print('Database created successfully.')

if __name__ == '__main__':
    create_database()
    app.run(port=5001, debug=True)