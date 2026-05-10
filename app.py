from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-12345'

# База данных
db_path = '/tmp/forum.db'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ========== МОДЕЛИ ==========
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_owner = db.Column(db.Boolean, default=False)  # ← Защита владельца
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    evidence = db.Column(db.Text, nullable=True)
    priority = db.Column(db.String(20), default='Средний')
    contact = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='Ожидание')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    moderator_reply = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ========== ДЕКОРАТОРЫ ==========
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Доступ запрещён. Требуются права администратора.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Пожалуйста, войдите в аккаунт.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ========== СОЗДАНИЕ ТАБЛИЦ И ВЛАДЕЛЬЦА ==========
with app.app_context():
    db.create_all()
    
    # Создаём владельца (админа, которого нельзя лишить прав)
    owner = User.query.filter_by(username='admin').first()
    if not owner:
        owner = User(username='admin', password='admin123', is_admin=True, is_owner=True)
        db.session.add(owner)
        db.session.commit()
        print("✅ Создан владелец: admin / admin123")
    else:
        # Если admin уже есть, но не owner — делаем owner
        if not owner.is_owner:
            owner.is_owner = True
            owner.is_admin = True
            db.session.commit()
            print("✅ Пользователь admin назначен владельцем")

# ========== МАРШРУТЫ ==========
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            flash(f'Добро пожаловать, {username}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверный логин или пароль', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not username or not password:
            flash('Заполните все поля', 'error')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует', 'error')
            return redirect(url_for('register'))
        
        new_user = User(username=username, password=password, is_admin=False, is_owner=False)
        db.session.add(new_user)
        db.session.commit()
        flash('Регистрация успешна! Теперь войдите.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из аккаунта', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', is_admin=session.get('is_admin'), username=session.get('username'))

@app.route('/rules')
@login_required
def rules():
    return render_template('rules.html')

@app.route('/faq')
@login_required
def faq():
    return render_template('faq.html')

@app.route('/complaints', methods=['GET', 'POST'])
@login_required
def complaints():
    if request.method == 'POST':
        topic = request.form.get('topic')
        description = request.form.get('description')
        evidence = request.form.get('evidence')
        priority = request.form.get('priority')
        contact = request.form.get('contact')

        if not topic or not description:
            flash('Пожалуйста, заполните обязательные поля: тема и описание.', 'error')
            return redirect(url_for('complaints'))

        new_complaint = Complaint(
            topic=topic,
            description=description,
            evidence=evidence,
            priority=priority,
            contact=contact,
            status='Ожидание',
            user_id=session.get('user_id')
        )
        db.session.add(new_complaint)
        db.session.commit()
        flash('Жалоба подана успешно!', 'success')
        return redirect(url_for('complaints'))
    
    all_complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    return render_template('complaints.html', complaints=all_complaints, is_admin=session.get('is_admin'))

@app.route('/complaint/<int:id>')
@login_required
def view_complaint(id):
    complaint = Complaint.query.get_or_404(id)
    return render_template('complaint.html', complaint=complaint, is_admin=session.get('is_admin'))

@app.route('/complaint/<int:id>/reply', methods=['POST'])
@login_required
def add_reply(id):
    complaint = Complaint.query.get_or_404(id)
    
    if complaint.status == 'Решено':
        flash('❌ Жалоба решена, ответы запрещены!', 'error')
        return redirect(url_for('view_complaint', id=id))
    
    reply_text = request.form.get('reply_text')
    if reply_text:
        complaint.moderator_reply = reply_text
        db.session.commit()
        flash('✅ Ответ добавлен!', 'success')
    return redirect(url_for('view_complaint', id=id))

# ========== МОДЕРАЦИЯ (ТОЛЬКО ДЛЯ АДМИНОВ) ==========
@app.route('/moderation', methods=['GET', 'POST'])
@admin_required
def moderation():
    complaints_list = Complaint.query.order_by(Complaint.created_at.desc()).all()
    
    if request.method == 'POST':
        complaint_id = request.form.get('id')
        action = request.form.get('action')
        reply = request.form.get('reply')
        
        complaint = Complaint.query.get(complaint_id)
        if complaint:
            if action == 'processing':
                complaint.status = 'В обработке'
            elif action == 'resolved':
                complaint.status = 'Решено'
            elif action == 'pending':
                complaint.status = 'Ожидание'
            
            if reply:
                complaint.moderator_reply = reply
            
            db.session.commit()
            flash('Изменения применены.', 'success')
        return redirect(url_for('moderation'))
    
    return render_template('moderation.html', complaints=complaints_list, is_admin=True)

@app.route('/complaint/<int:id>/rename', methods=['POST'])
@admin_required
def rename_complaint(id):
    complaint = Complaint.query.get_or_404(id)
    new_title = request.form.get('new_title')
    if new_title:
        complaint.topic = new_title
        db.session.commit()
        flash('Название жалобы изменено!', 'success')
    return redirect(url_for('moderation'))

@app.route('/complaint/<int:id>/delete', methods=['POST'])
@admin_required
def delete_complaint(id):
    complaint = Complaint.query.get_or_404(id)
    db.session.delete(complaint)
    db.session.commit()
    flash('Жалоба удалена!', 'success')
    return redirect(url_for('moderation'))

# ========== АДМИН ПАНЕЛЬ (С ЗАЩИТОЙ ВЛАДЕЛЬЦА) ==========
@app.route('/admin_panel', methods=['GET', 'POST'])
@admin_required
def admin_panel():
    users = User.query.all()
    current_user_obj = User.query.get(session.get('user_id'))
    
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        action = request.form.get('action')
        user = User.query.get(user_id)
        
        # ЗАЩИТА: нельзя изменять владельца
        if user and user.is_owner:
            flash('❌ Нельзя изменить права владельца!', 'error')
            return redirect(url_for('admin_panel'))
        
        # Нельзя изменять самого себя
        if user and user.id == session.get('user_id'):
            flash('❌ Нельзя изменить свои права', 'error')
            return redirect(url_for('admin_panel'))
        
        if user:
            if action == 'make_admin':
                user.is_admin = True
                flash(f'✅ Права администратора выданы {user.username}', 'success')
            elif action == 'remove_admin':
                user.is_admin = False
                flash(f'❌ Права администратора забраны у {user.username}', 'success')
            db.session.commit()
        return redirect(url_for('admin_panel'))
    
    return render_template('admin_panel.html', users=users, current_user=current_user_obj)

if __name__ == '__main__':
    app.run(debug=True)

application = app
