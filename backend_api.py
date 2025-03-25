from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import requests
import sqlite3
from contextlib import contextmanager

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Database Configuration
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'ecommerce.db')

# Database Connection Management
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# Database Initialization
def init_db():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Enable Write-Ahead Logging and other optimizations
            cursor.execute('PRAGMA journal_mode=WAL')
            cursor.execute('PRAGMA synchronous=NORMAL')
            cursor.execute('PRAGMA cache_size=10000')
            cursor.execute('PRAGMA temp_store=MEMORY')
            
            # Create users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                )
            ''')
            
            # Create products table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS product (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    category TEXT,
                    description TEXT,
                    price REAL,
                    rentprice REAL,
                    size TEXT,
                    image TEXT,
                    rating_rate REAL,
                    rating_count INTEGER
                )
            ''')
            
            # Create cart_item table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cart_item (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    product_id TEXT NOT NULL,
                    quantity INTEGER DEFAULT 1,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES user (id),
                    FOREIGN KEY (product_id) REFERENCES product (id)
                )
            ''')
            
            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_username ON user (username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_email ON user (email)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_product_title ON product (title)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cart_user_id ON cart_item (user_id)')
            
            conn.commit()
            print('Database initialized successfully with optimized settings.')
    except Exception as e:
        print(f'Error initializing database: {str(e)}')
        raise

# Helper functions
def set_password(password):
    return generate_password_hash(password)

def check_password(password_hash, password):
    return check_password_hash(password_hash, password)

# User Database Operations
def create_user(username, email, password_hash):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO user (username, email, password_hash) VALUES (?, ?, ?)',
            (username, email, password_hash)
        )
        conn.commit()
        return cursor.lastrowid

def get_user_by_username(username):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM user WHERE username = ?', (username,))
        return cursor.fetchone()

def get_user_by_email(email):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM user WHERE email = ?', (email,))
        return cursor.fetchone()

# Product Database Operations
def get_products(search=None, page=1, per_page=5):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        query = 'SELECT * FROM product'
        params = []
        
        if search:
            query += ' WHERE title LIKE ?'
            params.append(f'%{search}%')
        
        # Get total count
        count_cursor = conn.cursor()
        count_cursor.execute(f'SELECT COUNT(*) FROM ({query})', params)
        total = count_cursor.fetchone()[0]
        
        # Add pagination
        query += ' LIMIT ? OFFSET ?'
        params.extend([per_page, (page - 1) * per_page])
        
        cursor.execute(query, params)
        products = cursor.fetchall()
        
        return products, total

def merge_product(product_data):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO product 
            (id, title, category, description, price, rentprice, size, image, rating_rate, rating_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            product_data['id'],
            product_data['title'],
            product_data['category'],
            product_data['description'],
            product_data['price'],
            product_data['rentprice'],
            product_data['size'],
            product_data['image'],
            product_data['rating_rate'],
            product_data['rating_count']
        ))
        conn.commit()

# Cart Database Operations
def get_cart_items(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT ci.*, p.title, p.price, p.image 
            FROM cart_item ci 
            JOIN product p ON ci.product_id = p.id 
            WHERE ci.user_id = ?
        ''', (user_id,))
        return cursor.fetchall()

def add_to_cart(user_id, product_id, quantity):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Check if item already exists
        cursor.execute(
            'SELECT quantity FROM cart_item WHERE user_id = ? AND product_id = ?',
            (user_id, product_id)
        )
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute(
                'UPDATE cart_item SET quantity = quantity + ? WHERE user_id = ? AND product_id = ?',
                (quantity, user_id, product_id)
            )
        else:
            cursor.execute(
                'INSERT INTO cart_item (user_id, product_id, quantity) VALUES (?, ?, ?)',
                (user_id, product_id, quantity)
            )
        
        conn.commit()

def update_cart_item(cart_item_id, quantity):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE cart_item SET quantity = ? WHERE id = ?',
            (quantity, cart_item_id)
        )
        conn.commit()
        return cursor.rowcount > 0

def remove_cart_item(cart_item_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cart_item WHERE id = ?', (cart_item_id,))
        conn.commit()
        return cursor.rowcount > 0

# Authentication Routes
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if get_user_by_username(data['username']):
        return jsonify({'error': 'Username already exists'}), 400
    
    if get_user_by_email(data['email']):
        return jsonify({'error': 'Email already exists'}), 400
    
    password_hash = set_password(data['password'])
    user_id = create_user(data['username'], data['email'], password_hash)
    
    return jsonify({'message': 'User registered successfully', 'user_id': user_id}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = get_user_by_username(data['username'])
    
    if user and check_password(user['password_hash'], data['password']):
        return jsonify({
            'message': 'Login successful',
            'user_id': user['id'],
            'username': user['username']
        })
    
    return jsonify({'error': 'Invalid username or password'}), 401

# Cart Routes
@app.route('/api/cart', methods=['GET'])
def get_cart():
    user_id = request.args.get('user_id')
    cart_items = get_cart_items(user_id)
    
    items = [{
        'id': item['id'],
        'product': {
            'id': item['product_id'],
            'title': item['title'],
            'price': item['price'],
            'image': item['image']
        },
        'quantity': item['quantity'],
        'added_at': item['added_at']
    } for item in cart_items]
    
    return jsonify({'cart_items': items})

@app.route('/api/cart/add', methods=['POST'])
def add_to_cart_route():
    data = request.get_json()
    user_id = data['user_id']
    product_id = data['product_id']
    quantity = data.get('quantity', 1)
    
    add_to_cart(user_id, product_id, quantity)
    return jsonify({'message': 'Item added to cart successfully'})

@app.route('/api/cart/update', methods=['PUT'])
def update_cart_item_route():
    data = request.get_json()
    success = update_cart_item(data['cart_item_id'], data['quantity'])
    
    if not success:
        return jsonify({'error': 'Cart item not found'}), 404
    
    return jsonify({'message': 'Cart item updated successfully'})

@app.route('/api/cart/remove', methods=['DELETE'])
def remove_from_cart():
    cart_item_id = request.args.get('cart_item_id')
    success = remove_cart_item(cart_item_id)
    
    if not success:
        return jsonify({'error': 'Cart item not found'}), 404
    
    return jsonify({'message': 'Item removed from cart successfully'})

# Product Routes
@app.route('/products', methods=['GET'])
def get_products_route():
    search = request.args.get('search')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 5))

    products, total = get_products(search, page, per_page)
    pages = (total + per_page - 1) // per_page

    result = [{
        'id': product['id'],
        'title': product['title'],
        'category': product['category'],
        'description': product['description'],
        'price': product['price'],
        'rentprice': product['rentprice'],
        'size': product['size'],
        'image': product['image'],
        'rating': {
            'rate': product['rating_rate'],
            'count': product['rating_count']
        }
    } for product in products]

    return jsonify({
        'products': result,
        'total': total,
        'pages': pages,
        'current_page': page
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
        product_data = {
            'id': product['_id'],
            'title': product['title'],
            'category': product['category'],
            'description': product['description'],
            'price': product['price'],
            'rentprice': product['rentprice'],
            'size': product['size'],
            'image': product['image'],
            'rating_rate': product['rating']['rate'],
            'rating_count': product['rating']['count']
        }
        merge_product(product_data)
    
    return jsonify({'message': 'Products fetched and stored successfully'}), 201

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
