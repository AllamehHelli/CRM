import os
from flask import Flask, render_template, request, redirect, url_for, flash, abort, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import jdatetime
import pytz
import pandas as pd
from io import BytesIO
from sqlalchemy import func, case, or_

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-key-that-should-be-changed')
db_url = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

def to_shamsi(gregorian_datetime):
    if gregorian_datetime is None: return ""
    tehran_tz = pytz.timezone("Asia/Tehran")
    local_time = gregorian_datetime.astimezone(tehran_tz)
    jalali_datetime = jdatetime.datetime.fromgregorian(datetime=local_time)
    return jalali_datetime.strftime('%Y/%m/%d - %H:%M')
app.jinja_env.filters['shamsi'] = to_shamsi

def get_status_display(status_en):
    statuses = {"New": ("جدید", "secondary"), "In Progress": ("در حال بررسی", "primary"), "Closed": ("بسته شده", "success")}
    return statuses.get(status_en, (status_en, "dark"))
app.jinja_env.globals.update(get_status_display=get_status_display)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.role == 'admin': abort(403)
        return f(*args, **kwargs)
    return decorated_function

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=True)
    created_tickets = db.relationship('Ticket', backref='creator', lazy=True, cascade="all, delete-orphan")
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    tickets = db.relationship('Ticket', backref='department', lazy=True)
    operators = db.relationship('User', backref='department', lazy=True)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    helli_code = db.Column(db.String(20), unique=True, nullable=True)
    national_id = db.Column(db.String(20), unique=True, nullable=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    grade = db.Column(db.String(20))
    student_mobile = db.Column(db.String(20), unique=True, nullable=True)
    parent_mobile = db.Column(db.String(20))
    tickets = db.relationship('Ticket', backref='student', lazy=True)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='New')
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=db.func.now(), server_default=db.func.now())
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/find_student')
@login_required
def find_student():
    search_term = request.args.get('term', '')
    if not search_term:
        return jsonify(None)

    student = Student.query.filter(
        or_(
            Student.national_id == search_term,
            Student.student_mobile == search_term,
            Student.helli_code == search_term
        )
    ).first()

    if student:
        return jsonify({
            'id': student.id,
            'first_name': student.first_name,
            'last_name': student.last_name,
            'helli_code': student.helli_code,
            'grade': student.grade,
            'student_mobile': student.student_mobile,
            'parent_mobile': student.parent_mobile
        })
    return jsonify(None)

@app.route('/')
@login_required
def index():
    departments = Department.query.all()
    if current_user.role == 'admin':
        tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
    elif current_user.role == 'operator':
        tickets = Ticket.query.filter_by(department_id=current_user.department_id).order_by(Ticket.created_at.desc()).all()
    else:
        tickets = Ticket.query.filter_by(creator_id=current_user.id).order_by(Ticket.created_at.desc()).all()
    return render_template('index.html', tickets=tickets, departments=departments)

@app.route('/create', methods=['POST'])
@login_required
def create():
    national_id = request.form.get('national_id')
    student_mobile = request.form.get('student_mobile')
    student_id = request.form.get('student_id')
    
    student = None
    if student_id:
        student = Student.query.get(student_id)
    
    if not student:
        if national_id:
            student = Student.query.filter_by(national_id=national_id).first()
        if not student and student_mobile:
            student = Student.query.filter_by(student_mobile=student_mobile).first()

    if student:
        # آپدیت اطلاعات دانش‌آموز موجود در صورت نیاز
        student.first_name = request.form['first_name']
        student.last_name = request.form['last_name']
        student.grade = request.form.get('grade')
        student.parent_mobile = request.form.get('parent_mobile')
        # ... سایر فیلدها ...
    else:
        # ایجاد دانش‌آموز جدید
        student = Student(
            national_id=national_id,
            student_mobile=student_mobile,
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            helli_code=request.form.get('helli_code'),
            grade=request.form.get('grade'),
            parent_mobile=request.form.get('parent_mobile')
        )
        db.session.add(student)
    
    db.session.flush() # برای گرفتن ID دانش‌آموز قبل از کامیت نهایی
    
    new_ticket = Ticket(
        title=request.form['title'],
        description=request.form['description'],
        department_id=request.form['department_id'],
        creator_id=current_user.id,
        student_id=student.id
    )
    db.session.add(new_ticket)
    db.session.commit()
    flash('تیکت با موفقیت ثبت شد.', 'success')
    return redirect(url_for('index'))

# ... (تمام مسیرهای دیگر بدون تغییر باقی می‌مانند)
# فقط مسیرهای ticket_detail و index را برای نمایش اطلاعات جدید دانش‌آموز به‌روز می‌کنیم
@app.route('/login', methods=['GET', 'POST'])
def login():
    if User.query.first() is None: return redirect(url_for('register_first_admin'))
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user); return redirect(url_for('index'))
        flash('نام کاربری یا رمز عبور اشتباه است.', 'danger')
    return render_template('login.html')
@app.route('/register_first_admin', methods=['GET', 'POST'])
def register_first_admin():
    if User.query.first() is not None: return redirect(url_for('login'))
    if request.method == 'POST':
        new_user = User(username=request.form['username'], first_name=request.form['first_name'], last_name=request.form['last_name'], role='admin')
        new_user.set_password(request.form['password'])
        db.session.add(new_user); db.session.commit()
        flash('کاربر ادمین با موفقیت ایجاد شد. لطفاً وارد شوید.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))
@app.route('/ticket/<int:ticket_id>')
@login_required
def ticket_detail(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    is_admin, is_creator, is_operator = current_user.role == 'admin', ticket.creator_id == current_user.id, (current_user.role == 'operator' and ticket.department_id == current_user.department_id)
    if not (is_admin or is_creator or is_operator): abort(403)
    return render_template('ticket_detail.html', ticket=ticket)
@app.route('/ticket/<int:ticket_id>/update', methods=['POST'])
@login_required
def update_status(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    is_admin, is_operator = current_user.role == 'admin', (current_user.role == 'operator' and ticket.department_id == current_user.department_id)
    if not (is_admin or is_operator): abort(403)
    ticket.status = request.form['status']
    db.session.commit()
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))
@app.route('/ticket/<int:ticket_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    db.session.delete(ticket); db.session.commit()
    return redirect(url_for('index'))
@app.route('/manage_users')
@login_required
@admin_required
def manage_users():
    users, departments = User.query.order_by(User.id).all(), Department.query.all()
    return render_template('manage_users.html', users=users, departments=departments)
@app.route('/add_user', methods=['POST'])
@login_required
@admin_required
def add_user():
    username, first_name, last_name, password, role = request.form['username'], request.form['first_name'], request.form['last_name'], request.form['password'], request.form['role']
    department_id = request.form.get('department_id')
    if User.query.filter_by(username=username).first(): flash(f'نام کاربری "{username}" تکراری است.', 'danger')
    else:
        new_user = User(username=username, first_name=first_name, last_name=last_name, role=role)
        if role == 'operator' and department_id: new_user.department_id = department_id
        new_user.set_password(password)
        db.session.add(new_user); db.session.commit()
        flash(f'کاربر "{username}" با موفقیت ایجاد شد.', 'success')
    return redirect(url_for('manage_users'))
@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user_to_edit = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user_to_edit.first_name, user_to_edit.last_name, user_to_edit.role = request.form['first_name'], request.form['last_name'], request.form['role']
        if user_to_edit.role == 'operator': user_to_edit.department_id = request.form.get('department_id')
        else: user_to_edit.department_id = None
        if request.form.get('password'): user_to_edit.set_password(request.form.get('password'))
        db.session.commit()
        return redirect(url_for('manage_users'))
    departments = Department.query.all()
    return render_template('edit_user.html', user=user_to_edit, departments=departments)
@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == current_user.id: flash('شما نمی‌توانید حساب کاربری خودتان را حذف کنید.', 'danger')
    else:
        user = User.query.get_or_404(user_id)
        db.session.delete(user); db.session.commit()
        flash(f'کاربر "{user.username}" حذف شد.', 'success')
    return redirect(url_for('manage_users'))
def create_default_departments():
    default_deps = ['کتابخوان', 'بازارهوشمند', 'آموزش', 'آزمون‌ها', 'عمومی']
    for dep_name in default_deps:
        if not Department.query.filter_by(name=dep_name).first():
            db.session.add(Department(name=dep_name))
    db.session.commit()

with app.app_context():
    db.create_all()
    create_default_departments()
