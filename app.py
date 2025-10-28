import os
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-key-that-should-be-changed')
db_url = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "برای دسترسی به این صفحه باید ابتدا وارد شوید."
login_manager.login_message_category = "info"

# --- دکوراتور برای محدود کردن دسترسی به ادمین ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403) # خطای Forbidden
        return f(*args, **kwargs)
    return decorated_function

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), default='counselor')
    created_tickets = db.relationship('Ticket', backref='creator', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    tickets = db.relationship('Ticket', backref='department', lazy=True)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_code = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='New')
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- مسیرهای ورود و خروج (بدون تغییر) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('نام کاربری یا رمز عبور اشتباه است.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('شما با موفقیت از سیستم خارج شدید.', 'info')
    return redirect(url_for('login'))

# --- مسیرهای اصلی برنامه با منطق دسترسی ---

@app.route('/')
@login_required
def index():
    departments = Department.query.all()
    # اگر کاربر ادمین است، همه تیکت‌ها را نشان بده
    if current_user.role == 'admin':
        tickets = Ticket.query.order_by(Ticket.id.desc()).all()
    # در غیر این صورت (مشاور)، فقط تیکت‌های خودش را نشان بده
    else:
        tickets = Ticket.query.filter_by(creator_id=current_user.id).order_by(Ticket.id.desc()).all()
    
    return render_template('index.html', tickets=tickets, departments=departments)

@app.route('/create', methods=['POST'])
@login_required
def create():
    # ... (بدون تغییر)
    student_code = request.form['student_code']
    title = request.form['title']
    description = request.form['description']
    department_id = request.form['department_id']
    new_ticket = Ticket(student_code=student_code, title=title, description=description, department_id=department_id, creator_id=current_user.id)
    db.session.add(new_ticket)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/ticket/<int:ticket_id>')
@login_required
def ticket_detail(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    # اگر کاربر ادمین نیست، بررسی کن که آیا این تیکت متعلق به خودش است یا نه
    if current_user.role != 'admin' and ticket.creator_id != current_user.id:
        abort(403) # اگر نیست، اجازه دسترسی نده
    return render_template('ticket_detail.html', ticket=ticket)

# --- مسیرهای مدیریت (آپدیت و حذف) فقط برای ادمین ---

@app.route('/ticket/<int:ticket_id>/update', methods=['POST'])
@login_required
@admin_required # فقط ادمین می‌تواند وضعیت را تغییر دهد
def update_status(ticket_id):
    ticket_to_update = Ticket.query.get_or_404(ticket_id)
    new_status = request.form['status']
    ticket_to_update.status = new_status
    db.session.commit()
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))

@app.route('/ticket/<int:ticket_id>/delete', methods=['POST'])
@login_required
@admin_required # فقط ادمین می‌تواند تیکت را حذف کند
def delete_ticket(ticket_id):
    ticket_to_delete = Ticket.query.get_or_404(ticket_id)
    db.session.delete(ticket_to_delete)
    db.session.commit()
    flash(f'تیکت شماره {ticket_to_delete.id} با موفقیت حذف شد.', 'success')
    return redirect(url_for('index'))

# --- بخش مدیریت کاربران (فقط برای ادمین) ---

@app.route('/manage_users')
@login_required
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('manage_users.html', users=users)

@app.route('/register', methods=['GET', 'POST'])
def register():
    # این تابع را تغییر می‌دهیم تا ادمین بتواند کاربران جدید بسازد
    # اگر کسی لاگین نکرده و کاربری وجود ندارد، به او اجازه ثبت نام اولین ادمین را می‌دهیم
    if not current_user.is_authenticated and User.query.first() is not None:
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form.get('role', 'counselor') # نقش را از فرم می‌گیریم

        if User.query.filter_by(username=username).first():
            flash('این نام کاربری قبلاً ثبت شده است.', 'danger')
            return redirect(url_for('manage_users') if current_user.is_authenticated else url_for('register'))
        
        new_user = User(username=username, role=role)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        flash(f'کاربر {username} با موفقیت ایجاد شد.', 'success')
        return redirect(url_for('manage_users') if current_user.is_authenticated else url_for('login'))
        
    # اگر اولین کاربر است که ثبت نام می‌کند
    if User.query.first() is None:
        return render_template('register.html', first_user=True)
    # اگر ادمین در حال ساخت کاربر جدید است
    elif current_user.is_authenticated and current_user.role == 'admin':
        return render_template('register.html', first_user=False)
    else:
        abort(403)


# --- راه‌اندازی اولیه (بدون تغییر) ---
def create_default_departments():
    default_deps = ['کتابخوان', 'بازارهوشمند', 'آموزش', 'آزمون‌ها', 'عمومی']
    for dep_name in default_deps:
        if not Department.query.filter_by(name=dep_name).first():
            db.session.add(Department(name=dep_name))
    db.session.commit()

with app.app_context():
    db.create_all()
    create_default_departments()
