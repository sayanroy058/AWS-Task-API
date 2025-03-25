from flask import Flask, request, jsonify
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# MySQL Configuration
DB_CONFIG = {
    "user": "avnadmin",
    "password": "AVNS_xp2SiYh4HLQytUi6AmO",
    "host": "mysql-a2397a7-deliveryotter-3338.h.aivencloud.com",
    "port": 15862,
    "database": "defaultdb"
}

# Establish connection to MySQL
def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

# Create Tables
def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(80) UNIQUE NOT NULL,
        email VARCHAR(120) UNIQUE NOT NULL,
        password_hash VARCHAR(128) NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id VARCHAR(100) PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        category VARCHAR(100),
        description TEXT,
        price FLOAT,
        rentprice FLOAT,
        size VARCHAR(50),
        image VARCHAR(255),
        rating_rate FLOAT,
        rating_count INT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cart_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        product_id VARCHAR(100) NOT NULL,
        quantity INT DEFAULT 1,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    cursor.close()
    conn.close()

# Authentication Routes
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE username = %s", (data['username'],))
    if cursor.fetchone():
        return jsonify({'error': 'Username already exists'}), 400
    
    cursor.execute("SELECT * FROM users WHERE email = %s", (data['email'],))
    if cursor.fetchone():
        return jsonify({'error': 'Email already exists'}), 400

    password_hash = generate_password_hash(data['password'])

    cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)", 
                   (data['username'], data['email'], password_hash))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({'message': 'User registered successfully'}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE username = %s", (data['username'],))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user and check_password_hash(user['password_hash'], data['password']):
        return jsonify({'message': 'Login successful', 'user_id': user['id'], 'username': user['username']})
    
    return jsonify({'error': 'Invalid username or password'}), 401

# Cart Routes
@app.route('/api/cart', methods=['GET'])
def get_cart():
    user_id = request.args.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT cart_items.id, cart_items.quantity, cart_items.added_at,
           products.id AS product_id, products.title, products.price, products.image
    FROM cart_items
    JOIN products ON cart_items.product_id = products.id
    WHERE cart_items.user_id = %s
    """, (user_id,))

    items = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify({'cart_items': items})

@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    data = request.get_json()
    
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM cart_items WHERE user_id = %s AND product_id = %s", 
                   (data['user_id'], data['product_id']))
    existing_item = cursor.fetchone()

    if existing_item:
        cursor.execute("UPDATE cart_items SET quantity = quantity + %s WHERE user_id = %s AND product_id = %s",
                       (data.get('quantity', 1), data['user_id'], data['product_id']))
    else:
        cursor.execute("INSERT INTO cart_items (user_id, product_id, quantity) VALUES (%s, %s, %s)",
                       (data['user_id'], data['product_id'], data.get('quantity', 1)))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'message': 'Item added to cart successfully'})

# Product Routes
@app.route('/products', methods=['GET'])
def get_products():
    search = request.args.get('search', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 5))
    offset = (page - 1) * per_page

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if search:
        query = "SELECT * FROM products WHERE title LIKE %s LIMIT %s OFFSET %s"
        cursor.execute(query, (f"%{search}%", per_page, offset))
    else:
        query = "SELECT * FROM products LIMIT %s OFFSET %s"
        cursor.execute(query, (per_page, offset))

    products = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) as total FROM products")
    total = cursor.fetchone()["total"]

    cursor.close()
    conn.close()

    return jsonify({'products': products, 'total': total, 'pages': (total // per_page) + 1, 'current_page': page})

@app.route('/fetch-products', methods=['GET'])
def fetch_products():
    url = 'http://3.250.87.6:3000/freelancer/products'
    response = requests.get(url)
    
    if response.status_code != 200:
        return jsonify({'error': 'Failed to fetch products'}), 500
    
    products = response.json()

    conn = get_db_connection()
    cursor = conn.cursor()

    for product in products:
        cursor.execute("""
        INSERT INTO products (id, title, category, description, price, rentprice, size, image, rating_rate, rating_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE title = VALUES(title), category = VALUES(category), description = VALUES(description),
                                price = VALUES(price), rentprice = VALUES(rentprice), size = VALUES(size),
                                image = VALUES(image), rating_rate = VALUES(rating_rate), rating_count = VALUES(rating_count)
        """, (product['_id'], product['title'], product['category'], product['description'], 
              product['price'], product['rentprice'], product['size'], product['image'], 
              product['rating']['rate'], product['rating']['count']))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'message': 'Products fetched and stored successfully'}), 201

if __name__ == '__main__':
    create_tables()
    app.run(debug=True)
