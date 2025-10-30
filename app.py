import os
from flask import Flask, render_template, request, redirect, url_for, flash, abort, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import jdatetime
import pytz
import pandas as pd
from io import BytesIO
from sqlalchemy import func

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

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_code = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='New')
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=db.func.now(), server_default=db.func.now())
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def index():
    # ... (این بخش بدون تغییر باقی می‌ماند)
    query = Ticket.query
    creators = []
    if current_user.role == 'admin':
        creators = User.query.order_by(User.first_name).all()
        f_department = request.args.get('department')
        f_creator = request.args.get('creator')
        f_status = request.args.get('status')
        f_start_date = request.args.get('start_date')
        f_end_date = request.args.get('end_date')
        if f_department: query = query.filter(Ticket.department_id == f_department)
        if f_creator: query = query.filter(Ticket.creator_id == f_creator)
        if f_status: query = query.filter(Ticket.status == f_status)
        if f_start_date:
            start_date_gregorian = jdatetime.datetime.strptime(f_start_date, '%Y/%m/%d').togregorian()
            query = query.filter(Ticket.created_at >= start_date_gregorian)
        if f_end_date:
            end_date_gregorian = jdatetime.datetime.strptime(f_end_date, '%Y/%m/%d').togregorian().replace(hour=23, minute=59, second=59)
            query = query.filter(Ticket.created_at <= end_date_gregorian)
        tickets = query.order_by(Ticket.created_at.desc()).all()
    elif current_user.role == 'operator':
        tickets = query.filter_by(department_id=current_user.department_id).order_by(Ticket.created_at.desc()).all()
    else: # counselor
        tickets = query.filter_by(creator_id=current_user.id).order_by(Ticket.created_at.desc()).all()
    departments = Department.query.all()
    return render_template('index.html', tickets=tickets, departments=departments, creators=creators)

# --- مسیر جدید برای داشبورد گزارش‌گیری ---
@app.route('/reports')
@login_required
@admin_required
def reports():
    # مدیریت بازه زمانی
    end_date_str = request.args.get('end_date', jdatetime.datetime.now().strftime('%Y/%m/%d'))
    start_date_str = request.args.get('start_date', (jdatetime.datetime.now() - jdatetime.timedelta(days=30)).strftime('%Y/%m/%d'))

    start_date = jdatetime.datetime.strptime(start_date_str, '%Y/%m/%d').togregorian()
    end_date = jdatetime.datetime.strptime(end_date_str, '%Y/%m/%d').togregorian().replace(hour=23, minute=59, second=59)

    # کوئری پایه برای بازه زمانی
    base_query = Ticket.query.filter(Ticket.created_at.between(start_date, end_date))

    # --- محاسبات KPI ---
    total_tickets = base_query.count()
    closed_tickets = base_query.filter(Ticket.status == 'Closed').count()
    open_tickets = total_tickets - closed_tickets
    
    # محاسبه میانگin زمان حل
    closed_tickets_with_time = base_query.filter(Ticket.status == 'Closed', Ticket.updated_at.isnot(None)).all()
    total_resolution_time = sum([(t.updated_at - t.created_at).total_seconds() for t in closed_tickets_with_time], 0)
    avg_resolution_seconds = total_resolution_time / len(closed_tickets_with_time) if closed_tickets_with_time else 0
    avg_resolution_days = round(avg_resolution_seconds / (24 * 3600), 1)

    # --- داده‌های نمودارها ---
    # نمودار توزیع بر اساس بخش
    tickets_by_dept = db.session.query(Department.name, func.count(Ticket.id)).join(Ticket).filter(Ticket.created_at.between(start_date, end_date)).group_by(Department.name).all()
    dept_chart_labels = [d[0] for d in tickets_by_dept]
    dept_chart_data = [d[1] for d in tickets_by_dept]

    # نمودار توزیع بر اساس وضعیت
    tickets_by_status = db.session.query(Ticket.status, func.count(Ticket.id)).filter(Ticket.created_at.between(start_date, end_date)).group_by(Ticket.status).all()
    status_chart_labels = [get_status_display(s[0])[0] for s in tickets_by_status]
    status_chart_data = [s[1] for s in tickets_by_status]
    
    # داده‌های جداول عملکرد
    counselor_performance = db.session.query(User.first_name, User.last_name, func.count(Ticket.id)).join(Ticket, User.id == Ticket.creator_id).filter(User.role == 'counselor', Ticket.created_at.between(start_date, end_date)).group_by(User.id).all()
    department_performance = db.session.query(Department.name, func.count(Ticket.id).label('total'), func.sum(case((Ticket.status == 'Closed', 1), else_=0)).label('closed')).join(Ticket).filter(Ticket.created_at.between(start_date, end_date)).group_by(Department.name).all()

    return render_template('reports.html',
                           start_date=start_date_str,
                           end_date=end_date_str,
                           total_tickets=total_tickets,
                           closed_tickets=closed_tickets,
                           open_tickets=open_tickets,
                           avg_resolution_days=avg_resolution_days,
                           dept_chart_labels=dept_chart_labels,
                           dept_chart_data=dept_chart_data,
                           status_chart_labels=status_chart_labels,
                           status_chart_data=status_chart_data,
                           counselor_performance=counselor_performance,
                           department_performance=department_performance)

# ... (تمام مسیرها و کدهای دیگر دقیقاً مانند قبل باقی می‌مانند) ...
