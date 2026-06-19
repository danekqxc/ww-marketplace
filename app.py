import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import os
from werkzeug.utils import secure_filename
import json

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')
app.secret_key = 'wwm_ultimate_stable_key_v1'

DB_PATH = 'wwm_database.db'
UPLOAD_FOLDER = 'images/uploads'
AVATAR_FOLDER = 'images/avatars'

for folder in [UPLOAD_FOLDER, AVATAR_FOLDER]:
    os.makedirs(folder, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['AVATAR_FOLDER'] = AVATAR_FOLDER

GAMES_CATALOG = {
    "1": "Minecraft",
    "2": "Steam",
    "3": "CS2",
    "4": "Gamer Services",
    "5": "Brawl Stars",
    "6": "Dota 2",
    "7": "Roblox"
}

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, email TEXT UNIQUE, password TEXT, avatar TEXT DEFAULT "default_avatar.png", balance REAL DEFAULT 1000.0)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT, price REAL, 
        category TEXT, status TEXT DEFAULT "active", description TEXT, game_id TEXT, details TEXT, image TEXT)''')
    cursor.execute('CREATE TABLE IF NOT EXISTS favorites (user_id INTEGER, product_id INTEGER, PRIMARY KEY (user_id, product_id))')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        product_id INTEGER, 
        sender_id INTEGER, 
        receiver_id INTEGER, 
        message TEXT, 
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        buyer_id INTEGER,
        seller_id INTEGER,
        amount REAL,
        status TEXT DEFAULT "active",
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER UNIQUE,
        product_id INTEGER,
        buyer_id INTEGER,
        seller_id INTEGER,
        rating INTEGER,
        comment TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        
    try:
        cursor.execute('ALTER TABLE orders ADD COLUMN amount REAL')
    except: pass
    try: # Добавляем колонку status, если ее нет
        cursor.execute('ALTER TABLE orders ADD COLUMN status TEXT DEFAULT "active"')
    except: pass

    cursor.execute('UPDATE users SET balance = 1000 WHERE balance < 1000')
    conn.commit()
    conn.close()

def get_user_rating(user_id):
    conn = get_db_connection()
    res = conn.execute('SELECT AVG(rating) as avg_r, COUNT(id) as count_r FROM reviews WHERE seller_id = ?', (user_id,)).fetchone()
    conn.close()
    if res and res['count_r'] > 0:
        return round(res['avg_r'], 1), res['count_r']
    return 0, 0

@app.context_processor
def inject_games():
    return dict(GAMES_CATALOG=GAMES_CATALOG)

@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = session.get('user_id', 0)
    cursor.execute('''
        SELECT p.*, u.username, 
        (SELECT COUNT(*) FROM favorites f WHERE f.user_id = ? AND f.product_id = p.id) as is_fav
        FROM products p 
        JOIN users u ON p.user_id = u.id 
        WHERE p.status = "active" 
        ORDER BY p.id DESC LIMIT 12
    ''', (user_id,))
    recent = cursor.fetchall()
    user_balance = 0.0
    if user_id:
        user_row = cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,)).fetchone()
        if user_row: user_balance = user_row['balance']
        else: session.clear()
    conn.close()
    return render_template('index.html', user=session.get('username'), user_balance=user_balance, recent_products=recent)

@app.route('/auth')
def auth_page():
    return render_template('auth.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)', 
                       (data['username'], data['email'], data['password']))
        conn.commit()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Логин уже занят"})
    finally:
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    user = cursor.execute('SELECT * FROM users WHERE (username = ? OR email = ?) AND password = ?', 
                          (data['login'], data['login'], data['password'])).fetchone()
    conn.close()
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Неверный логин или пароль"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/profile')
def profile():
    if 'user_id' not in session: return redirect(url_for('auth_page'))
    conn = get_db_connection()
    cursor = conn.cursor()
    uid = session['user_id']
    user_data = cursor.execute('SELECT * FROM users WHERE id = ?', (uid,)).fetchone()
    
    if not user_data:
        session.clear()
        conn.close()
        return redirect(url_for('auth_page'))
        
    products = cursor.execute('SELECT * FROM products WHERE user_id = ? ORDER BY id DESC', (uid,)).fetchall()
    
    active_deals = cursor.execute('''
        SELECT DISTINCT p.id as product_id, p.title, p.price, u.username as seller_name,
        o.status as order_status, o.id as order_id
        FROM products p
        JOIN users u ON p.user_id = u.id
        LEFT JOIN orders o ON p.id = o.product_id AND (o.buyer_id = ? OR o.seller_id = ?)
        LEFT JOIN messages m ON p.id = m.product_id AND (m.sender_id = ? OR m.receiver_id = ?)
        WHERE (p.user_id != ? AND (o.status = 'active' OR (o.id IS NULL AND m.id IS NOT NULL)))
    ''', (uid, uid, uid, uid, uid)).fetchall()
    
    completed_orders = cursor.execute('''SELECT o.*, p.title, p.price, u.username as seller_name, r.id as review_id, r.rating, r.comment
                                       FROM orders o 
                                       JOIN products p ON o.product_id = p.id 
                                       JOIN users u ON o.seller_id = u.id 
                                       LEFT JOIN reviews r ON o.id = r.order_id
                                       WHERE o.buyer_id = ? AND o.status = "completed"
                                       ORDER BY o.timestamp DESC''', (uid,)).fetchall()

    completed_sales = cursor.execute('''SELECT o.*, p.title, p.price, u.username as buyer_name, r.rating, r.comment
                                      FROM orders o 
                                      JOIN products p ON o.product_id = p.id 
                                      JOIN users u ON o.buyer_id = u.id 
                                      LEFT JOIN reviews r ON o.id = r.order_id
                                      WHERE o.seller_id = ? AND o.status = "completed"
                                      ORDER BY o.timestamp DESC''', (uid,)).fetchall()

    avg_rating, review_count = get_user_rating(uid)
    conn.close()
    return render_template('profile.html', user=user_data, products=products, 
                           active_deals=active_deals, completed_orders=completed_orders, 
                           completed_sales=completed_sales, rating=avg_rating, review_count=review_count)

@app.route('/reviews/<username>')
def user_reviews(username):
    conn = get_db_connection()
    target_user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    if not target_user:
        conn.close()
        return "Пользователь не найден", 404
    
    reviews = conn.execute('''
        SELECT r.*, p.title, u.username as buyer_name, o.amount
        FROM reviews r
        JOIN products p ON r.product_id = p.id
        JOIN users u ON r.buyer_id = u.id
        JOIN orders o ON r.order_id = o.id
        WHERE r.seller_id = ? ORDER BY r.timestamp DESC
    ''', (target_user['id'],)).fetchall()
    
    avg_rating, review_count = get_user_rating(target_user['id'])
    conn.close()
    return render_template('reviews.html', target_user=target_user, reviews=reviews, 
                           rating=avg_rating, count=review_count, user=session.get('username'))

@app.route('/leave_review', methods=['POST'])
def leave_review():
    if 'user_id' not in session: return jsonify({"success": False})
    data = request.get_json()
    conn = get_db_connection()
    order = conn.execute('SELECT * FROM orders WHERE id = ? AND buyer_id = ? AND status = "completed"', 
                         (data['order_id'], session['user_id'])).fetchone()
    
    if not order:
        conn.close()
        return jsonify({"success": False, "message": "Сделка не завершена"})
    
    try:
        conn.execute('''INSERT INTO reviews (order_id, product_id, buyer_id, seller_id, rating, comment)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (order['id'], order['product_id'], session['user_id'], order['seller_id'], 
                      data['rating'], data['comment']))
        conn.commit()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Отзыв уже оставлен"})
    finally:
        conn.close()

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    conn = get_db_connection()
    user_id = session.get('user_id', 0)
    item = conn.execute('''
        SELECT p.*, u.username, u.avatar, u.id as seller_id,
        (SELECT COUNT(*) FROM favorites f WHERE f.user_id = ? AND f.product_id = p.id) as is_fav
        FROM products p 
        JOIN users u ON p.user_id = u.id 
        WHERE p.id = ?
    ''', (user_id, product_id)).fetchone()
    
    user_balance = 0.0
    if user_id:
        user_row = conn.execute('SELECT balance FROM users WHERE id = ?', (user_id,)).fetchone()
        if user_row: user_balance = user_row['balance']

    avg_rating, review_count = get_user_rating(item['seller_id']) if item else (0,0)
    conn.close()
    if not item: return "Товар не найден", 404
    return render_template('product_detail.html', user=session.get('username'), user_balance=user_balance, 
                           item=item, rating=avg_rating, review_count=review_count)

@app.route('/purchase/<int:product_id>')
def purchase_page(product_id):
    if 'user_id' not in session: return redirect(url_for('auth_page'))
    conn = get_db_connection()
    
    order_id = request.args.get('order_id', type=int)
    
    order = None
    if order_id:
        order = conn.execute('SELECT * FROM orders WHERE id = ? AND (buyer_id = ? OR seller_id = ?)', 
                             (order_id, session['user_id'], session['user_id'])).fetchone()
        if not order:
            conn.close()
            return "Сделка не найдена или у вас нет доступа", 404
        product_id = order['product_id']
    else:
        # Ищем любой последний заказ для этого товара, где пользователь участвует (как покупатель или продавец)
        order = conn.execute('''SELECT * FROM orders 
                                WHERE product_id = ? AND (buyer_id = ? OR seller_id = ?) 
                                ORDER BY id DESC LIMIT 1''',
                             (product_id, session['user_id'], session['user_id'])).fetchone()

    item = conn.execute('SELECT p.*, u.username, u.id as seller_id FROM products p JOIN users u ON p.user_id = u.id WHERE p.id = ?', (product_id,)).fetchone()
    
    user_balance_row = conn.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    review = None
    if order:
        review = conn.execute('SELECT * FROM reviews WHERE order_id = ?', (order['id'],)).fetchone()

    avg_rating, review_count = get_user_rating(item['seller_id']) if item else (0,0)
    conn.close()
    if not item: return "Товар не найден", 404
    return render_template('purchase.html', user=session.get('username'), item=item, 
                           user_balance=user_balance_row['balance'] if user_balance_row else 0, 
                           order=order, review=review,
                           rating=avg_rating, review_count=review_count)

@app.route('/buy_product', methods=['POST'])
def buy_product():
    if 'user_id' not in session: return jsonify({"success": False, "message": "Войдите"})
    pid = request.get_json().get('product_id')
    uid = session['user_id']
    conn = get_db_connection()
    try:
        product = conn.execute('SELECT * FROM products WHERE id = ?', (pid,)).fetchone()
        user = conn.execute('SELECT balance FROM users WHERE id = ?', (uid,)).fetchone()
        if not product or product['status'] != 'active': return jsonify({"success": False, "message": "Недоступно"})
        if product['user_id'] == uid: return jsonify({"success": False, "message": "Свой товар"})
        if user['balance'] < product['price']: return jsonify({"success": False, "message": "Мало денег"})
        conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (product['price'], uid))
        conn.execute('INSERT INTO orders (product_id, buyer_id, seller_id, amount, status) VALUES (?, ?, ?, ?, "active")', 
                       (pid, uid, product['user_id'], product['price']))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally: conn.close()

@app.route('/confirm_order', methods=['POST'])
def confirm_order():
    if 'user_id' not in session: return jsonify({"success": False})
    order_id = request.get_json().get('order_id')
    uid = session['user_id']
    conn = get_db_connection()
    try:
        order = conn.execute('SELECT * FROM orders WHERE id = ? AND buyer_id = ? AND status = "active"', (order_id, uid)).fetchone()
        if not order: return jsonify({"success": False, "message": "Не найдено"})
        conn.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (order['amount'], order['seller_id']))
        conn.execute('UPDATE orders SET status = "completed" WHERE id = ?', (order_id,))
        conn.execute('UPDATE products SET status = "sold" WHERE id = ?', (order['product_id'],))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally: conn.close()

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'user_id' not in session: return jsonify({"success": False})
    data = request.get_json()
    conn = get_db_connection()
    receiver_id = data.get('receiver_id')
    if not receiver_id:
        product = conn.execute('SELECT user_id FROM products WHERE id = ?', (data['product_id'],)).fetchone()
        receiver_id = product['user_id'] if product else 0
    conn.execute('INSERT INTO messages (product_id, sender_id, receiver_id, message) VALUES (?, ?, ?, ?)',
                   (data['product_id'], session['user_id'], receiver_id, data['message']))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/get_messages/<int:product_id>')
def get_messages(product_id):
    if 'user_id' not in session: return jsonify([])
    other_id = request.args.get('other_id')
    conn = get_db_connection()
    if not other_id:
        product = conn.execute('SELECT user_id FROM products WHERE id = ?', (product_id,)).fetchone()
        other_id = product['user_id'] if product else 0
    messages = conn.execute('''SELECT m.*, u.username as sender_name FROM messages m 
                                 JOIN users u ON m.sender_id = u.id 
                                 WHERE product_id = ? AND 
                                 ((m.sender_id = ? AND m.receiver_id = ?) OR (m.sender_id = ? AND m.receiver_id = ?))
                                 ORDER BY timestamp ASC''', 
                              (product_id, session['user_id'], other_id, other_id, session['user_id'])).fetchall()
    conn.close()
    return jsonify([dict(m) for m in messages])

@app.route('/upload_avatar', methods=['POST'])
def upload_avatar():
    if 'user_id' not in session: return jsonify({"success": False})
    file = request.files['avatar']
    filename = secure_filename(f"av_{session['user_id']}_{file.filename}")
    file.save(os.path.join(app.config['AVATAR_FOLDER'], filename))
    conn = get_db_connection()
    conn.execute('UPDATE users SET avatar = ? WHERE id = ?', (filename, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/add_product', methods=['POST'])
def add_product():
    if 'user_id' not in session: return jsonify({"success": False})
    title = request.form.get('title')
    price = request.form.get('price')
    game_id = request.form.get('game_id')
    description = request.form.get('description')
    img_name = None
    if 'image' in request.files:
        f = request.files['image']
        if f and f.filename != '':
            img_name = secure_filename(f"p_{session['user_id']}_{f.filename}")
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], img_name))

    conn = get_db_connection()
    conn.execute('''INSERT INTO products (user_id, title, price, category, status, description, game_id, image)
                      VALUES (?, ?, ?, 'Games', 'active', ?, ?, ?)''', 
                   (session['user_id'], title, price, description, game_id, img_name))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/get_interacted_users/<int:product_id>')
def get_interacted_users(product_id):
    if 'user_id' not in session: return jsonify([])
    conn = get_db_connection()
    users = conn.execute('''
        SELECT DISTINCT u.id, u.username FROM messages m
        JOIN users u ON (m.sender_id = u.id OR m.receiver_id = u.id)
        WHERE m.product_id = ? AND u.id != (SELECT user_id FROM products WHERE id = ?)
        AND u.id IN (SELECT buyer_id FROM orders WHERE product_id = ? AND status = 'active' UNION SELECT sender_id FROM messages WHERE product_id = ?)
    ''', (product_id, product_id, product_id, product_id)).fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/search_api')
def search_api():
    q = request.args.get('q', '').lower()
    return jsonify([{"id": k, "name": v} for k, v in GAMES_CATALOG.items() if q in v.lower()])

@app.route('/listings/<game_id>')
def listings(game_id):
    name = GAMES_CATALOG.get(game_id, "Unknown")
    conn = get_db_connection()
    user_id = session.get('user_id', 0)
    items = conn.execute('''
        SELECT p.*, u.username, 
        (SELECT COUNT(*) FROM favorites f WHERE f.user_id = ? AND f.product_id = p.id) as is_fav
        FROM products p JOIN users u ON p.user_id = u.id WHERE p.game_id = ? AND p.status = 'active'
    ''', (user_id, game_id)).fetchall()
    conn.close()
    return render_template('listings.html', user=session.get('username'), game_name=name, items=items)

@app.route('/favorites')
def favorites_page():
    if 'user_id' not in session: return redirect(url_for('auth_page'))
    conn = get_db_connection()
    items = conn.execute('''SELECT p.*, u.username, 1 as is_fav FROM favorites f 
                      JOIN products p ON f.product_id = p.id 
                      JOIN users u ON p.user_id = u.id WHERE f.user_id = ?''', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('favorites.html', user=session.get('username'), items=items)

@app.route('/toggle_favorite', methods=['POST'])
def toggle_favorite():
    if 'user_id' not in session: return jsonify({"success": False})
    pid = request.get_json().get('product_id')
    uid = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM favorites WHERE user_id = ? AND product_id = ?', (uid, pid))
    if cursor.fetchone():
        cursor.execute('DELETE FROM favorites WHERE user_id = ? AND product_id = ?', (uid, pid))
        st = 'removed'
    else:
        cursor.execute('INSERT INTO favorites (user_id, product_id) VALUES (?, ?)', (uid, pid))
        st = 'added'
    conn.commit()
    conn.close()
    return jsonify({"success": True, "status": st})

@app.route('/android')
def android_page():
    return render_template('android.html')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
