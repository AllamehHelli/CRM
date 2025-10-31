import os
from flask import Flask, render_template, request, redirect, url_for, flash, abort, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta, date
import jdatetime
import pytz
import pandas as pd
from io import BytesIO, StringIO
from sqlalchemy import func, case, or_
import google.generativeai as genai

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-key-that-should-be-changed')
db_url = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- اصلاح نهایی و صحیح برای راه‌اندازی API ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        genai_model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception as e:
        print(f"Could not configure Gemini client: {e}")
        genai_model = None
else:
    genai_model = None

def to_shamsi(gregorian_dt):
    if gregorian_dt is None: return ""
    if isinstance(gregorian_dt, date) and not isinstance(gregorian_dt, datetime):
        return jdatetime.date.fromgregorian(date=gregorian_dt).strftime('%Y/%m/%d')
    tehran_tz = pytz.timezone("Asia/Tehran")
    local_time = gregorian_dt.astimezone(tehran_tz)
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
    comments = db.relationship('Comment', backref='author', lazy=True)
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
    gender = db.Column(db.String(10))
    grade = db.Column(db.String(20))
    province = db.Column(db.String(50))
    student_mobile = db.Column(db.String(20), unique=True, nullable=True)
    parent_mobile = db.Column(db.String(20))
    emergency_mobile = db.Column(db.String(20))
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
    comments = db.relationship('Comment', backref='ticket', lazy=True, cascade="all, delete-orphan")

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)

def generate_ai_summary(ticket_descriptions, department_name):
    if not genai_model or not ticket_descriptions:
        return "خلاصه در دسترس نیست."
    try:
        prompt = f"""شما یک تحلیلگر متخصص CRM هستید. وظیفه شما تحلیل لیستی از توضیحات تیکت‌های اخیر برای بخش '{department_name}' و ارائه خلاصه‌ای کوتاه و کاربردی برای یک مدیر است. بر روی شناسایی موضوعات تکراری، مشکلات رایج و علل ریشه‌ای تمرکز کنید. تیکت‌ها را لیست نکنید. اطلاعات را در یک پاراگراف منسجم ترکیب کنید. خلاصه باید به زبان فارسی باشد. توضیحات تیکت‌ها: {' - '.join(ticket_descriptions)}"""
        response = genai_model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return f"خطا در تولید خلاصه: {e}"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ... (تمام مسیرهای دیگر بدون هیچ تغییری باقی می‌مانند)
@app.route('/')
@login_required
def index():
    departments = Department.query.all()
    query = Ticket.query
    if current_user.role == 'admin':
        tickets = query.order_by(Ticket.created_at.desc()).limit(10).all()
    elif current_user.role == 'operator':
        tickets = query.filter_by(department_id=current_user.department_id).order_by(Ticket.created_at.desc()).limit(10).all()
    else:
        tickets = query.filter_by(creator_id=current_user.id).order_by(Ticket.created_at.desc()).limit(10).all()
    return render_template('index.html', tickets=tickets, departments=departments)
@app.route('/tickets')
@login_required
def tickets_list():
    query = Ticket.query
    creators = []
    if current_user.role == 'admin':
        creators = User.query.order_by(User.first_name).all()
        f_department, f_creator, f_status, f_start_date, f_end_date, f_helli_code = request.args.get('department'), request.args.get('creator'), request.args.get('status'), request.args.get('start_date'), request.args.get('end_date'), request.args.get('helli_code')
        if f_department: query = query.filter(Ticket.department_id == f_department)
        if f_creator: query = query.filter(Ticket.creator_id == f_creator)
        if f_status: query = query.filter(Ticket.status == f_status)
        if f_start_date: query = query.filter(Ticket.created_at >= jdatetime.datetime.strptime(f_start_date, '%Y/%m/%d').togregorian())
        if f_end_date: query = query.filter(Ticket.created_at <= jdatetime.datetime.strptime(f_end_date, '%Y/%m/%d').togregorian().replace(hour=23, minute=59, second=59))
        if f_helli_code: query = query.join(Student).filter(Student.helli_code == f_helli_code)
        tickets = query.order_by(Ticket.created_at.desc()).all()
    elif current_user.role == 'operator':
        tickets = query.filter_by(department_id=current_user.department_id).order_by(Ticket.created_at.desc()).all()
    else: # counselor
        tickets = query.filter_by(creator_id=current_user.id).order_by(Ticket.created_at.desc()).all()
    departments = Department.query.all()
    return render_template('tickets_list.html', tickets=tickets, departments=departments, creators=creators)
@app.route('/find_student')
@login_required
def find_student():
    search_term = request.args.get('term', '')
    if not search_term or len(search_term) < 3: return jsonify(None)
    student = Student.query.filter(or_(Student.national_id == search_term, Student.student_mobile == search_term, Student.helli_code == search_term)).first()
    if student:
        return jsonify({'id': student.id, 'first_name': student.first_name, 'last_name': student.last_name, 'helli_code': student.helli_code, 'grade': student.grade, 'student_mobile': student.student_mobile, 'parent_mobile': student.parent_mobile, 'national_id': student.national_id})
    return jsonify(None)
@app.route('/create', methods=['POST'])
@login_required
def create():
    student_id = request.form.get('student_id')
    student = None
    if student_id: student = Student.query.get(student_id)
    if not student:
        national_id, student_mobile = request.form.get('national_id'), request.form.get('student_mobile')
        if national_id: student = Student.query.filter_by(national_id=national_id).first()
        if not student and student_mobile: student = Student.query.filter_by(student_mobile=student_mobile).first()
    if student:
        student.first_name, student.last_name, student.grade, student.parent_mobile = request.form['first_name'], request.form['last_name'], request.form.get('grade'), request.form.get('parent_mobile')
    else:
        student = Student(national_id=request.form.get('national_id') or None, student_mobile=request.form.get('student_mobile') or None, first_name=request.form['first_name'], last_name=request.form['last_name'], helli_code=request.form.get('helli_code') or None, grade=request.form.get('grade'), parent_mobile=request.form.get('parent_mobile'))
        db.session.add(student)
    db.session.flush()
    new_ticket = Ticket(title=request.form['title'], description=request.form['description'], department_id=request.form['department_id'], creator_id=current_user.id, student_id=student.id)
    db.session.add(new_ticket)
    db.session.commit()
    return redirect(url_for('index'))
@app.route('/reports')
@login_required
@admin_required
def reports():
    end_date_str = request.args.get('end_date', jdatetime.datetime.now().strftime('%Y/%m/%d'))
    start_date_str = request.args.get('start_date', (jdatetime.datetime.now() - jdatetime.timedelta(days=30)).strftime('%Y/%m/%d'))
    start_date = jdatetime.datetime.strptime(start_date_str, '%Y/%m/%d').togregorian()
    end_date = jdatetime.datetime.strptime(end_date_str, '%Y/%m/%d').togregorian().replace(hour=23, minute=59, second=59)
    base_query = Ticket.query.filter(Ticket.created_at.between(start_date, end_date))
    total_tickets, closed_tickets = base_query.count(), base_query.filter(Ticket.status == 'Closed').count()
    open_tickets = total_tickets - closed_tickets
    closed_tickets_with_time = base_query.filter(Ticket.status == 'Closed', Ticket.updated_at.isnot(None)).all()
    total_resolution_time = sum([(t.updated_at - t.created_at).total_seconds() for t in closed_tickets_with_time], 0)
    avg_resolution_seconds = total_resolution_time / len(closed_tickets_with_time) if closed_tickets_with_time else 0
    avg_resolution_days = round(avg_resolution_seconds / (24 * 3600), 1)
    oldest_open_ticket = Ticket.query.filter(Ticket.status != 'Closed').order_by(Ticket.created_at.asc()).first()
    oldest_open_ticket_age = (datetime.now(pytz.utc) - oldest_open_ticket.created_at).days if oldest_open_ticket else 0
    test_summary = generate_ai_summary(["تیکت تست ۱", "تیکت تست ۲"], "بخش آزمایشی")
    print("AI Summary:", test_summary)
    tickets_by_dept = db.session.query(Department.name, func.count(Ticket.id)).join(Ticket).filter(Ticket.created_at.between(start_date, end_date)).group_by(Department.name).all()
    dept_chart_labels, dept_chart_data = [d[0] for d in tickets_by_dept], [d[1] for d in tickets_by_dept]
    tickets_by_status = db.session.query(Ticket.status, func.count(Ticket.id)).filter(Ticket.created_at.between(start_date, end_date)).group_by(Ticket.status).all()
    status_chart_labels, status_chart_data = [get_status_display(s[0])[0] for s in tickets_by_status], [s[1] for s in tickets_by_status]
    daily_trend_query = db.session.query(func.date(Ticket.created_at), func.count(Ticket.id)).filter(Ticket.created_at.between(start_date, end_date)).group_by(func.date(Ticket.created_at)).order_by(func.date(Ticket.created_at)).all()
    trend_labels, trend_data = [to_shamsi(d[0]) for d in daily_trend_query], [d[1] for d in daily_trend_query]
    operator_performance = db.session.query(User.first_name, User.last_name, Department.name, func.count(Ticket.id).label('total'), func.sum(case((Ticket.status == 'Closed', 1), else_=0)).label('closed')).join(Ticket, Department.id == Ticket.department_id).join(User, User.department_id == Department.id).filter(User.role == 'operator', Ticket.created_at.between(start_date, end_date)).group_by(User.id, Department.name).all()
    counselor_performance = db.session.query(User.first_name, User.last_name, func.count(Ticket.id)).join(Ticket, User.id == Ticket.creator_id).filter(User.role == 'counselor', Ticket.created_at.between(start_date, end_date)).group_by(User.id).all()
    department_performance = db.session.query(Department.name, func.count(Ticket.id).label('total'), func.sum(case((Ticket.status == 'Closed', 1), else_=0)).label('closed')).join(Ticket).filter(Ticket.created_at.between(start_date, end_date)).group_by(Department.name).all()
    return render_template('reports.html', start_date=start_date_str, end_date=end_date_str, total_tickets=total_tickets, closed_tickets=closed_tickets, open_tickets=open_tickets, avg_resolution_days=avg_resolution_days, oldest_open_ticket_age=oldest_open_ticket_age, dept_chart_labels=dept_chart_labels, dept_chart_data=dept_chart_data, status_chart_labels=status_chart_labels, status_chart_data=status_chart_data, trend_labels=trend_labels, trend_data=trend_data, counselor_performance=counselor_performance, operator_performance=operator_performance, department_performance=department_performance)
@app.route('/export')
@login_required
@admin_required
def export_excel():
    query = Ticket.query
    f_department, f_creator, f_status, f_start_date, f_end_date, f_helli_code = request.args.get('department'), request.args.get('creator'), request.args.get('status'), request.args.get('start_date'), request.args.get('end_date'), request.args.get('helli_code')
    if f_department: query = query.filter(Ticket.department_id == f_department)
    if f_creator: query = query.filter(Ticket.creator_id == f_creator)
    if f_status: query = query.filter(Ticket.status == f_status)
    if f_start_date: query = query.filter(Ticket.created_at >= jdatetime.datetime.strptime(f_start_date, '%Y/%m/%d').togregorian())
    if f_end_date: query = query.filter(Ticket.created_at <= jdatetime.datetime.strptime(f_end_date, '%Y/%m/%d').togregorian().replace(hour=23, minute=59, second=59))
    if f_helli_code: query = query.join(Student).filter(Student.helli_code == f_helli_code)
    tickets_to_export = query.order_by(Ticket.created_at.desc()).all()
    data = [{'شناسه': t.id, 'عنوان': t.title, 'حلی کد': t.student.helli_code, 'شرح مشکل': t.description, 'وضعیت': get_status_display(t.status)[0], 'بخش': t.department.name, 'ایجاد کننده': f"{t.creator.first_name} {t.creator.last_name}", 'تاریخ ایجاد (شمسی)': to_shamsi(t.created_at)} for t in tickets_to_export]
    df = pd.DataFrame(data)
    output = BytesIO()
    df.to_excel(output, index=False, sheet_name='گزارش تیکت‌ها', engine='openpyxl')
    output.seek(0)
    return send_file(output, download_name='report.xlsx', as_attachment=True)
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
    departments = Department.query.all()
    return render_template('ticket_detail.html', ticket=ticket, departments=departments)
@app.route('/ticket/<int:ticket_id>/comment', methods=['POST'])
@login_required
def add_comment(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    is_admin = current_user.role == 'admin'
    is_operator = (current_user.role == 'operator' and ticket.department_id == current_user.department_id)
    if not (is_admin or is_operator): abort(403)
    content = request.form.get('content')
    if content:
        new_comment = Comment(content=content, user_id=current_user.id, ticket_id=ticket.id)
        db.session.add(new_comment); db.session.commit()
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))
@app.route('/ticket/<int:ticket_id>/reassign', methods=['POST'])
@login_required
@admin_required
def reassign_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    new_department_id = request.form.get('department_id')
    if new_department_id:
        ticket.department_id = new_department_id
        db.session.commit()
        flash(f'تیکت به بخش جدید ارجاع داده شد.', 'success')
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))
@app.route('/ticket/<int:ticket_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    if not (current_user.role == 'admin' or ticket.creator_id == current_user.id): abort(403)
    if request.method == 'POST':
        ticket.title, ticket.department_id, ticket.description = request.form['title'], request.form['department_id'], request.form['description']
        db.session.commit()
        return redirect(url_for('ticket_detail', ticket_id=ticket.id))
    departments = Department.query.all()
    return render_template('edit_ticket.html', ticket=ticket, departments=departments)
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
@app.route('/manage_students')
@login_required
@admin_required
def manage_students():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    query = Student.query.order_by(Student.last_name)
    if search:
        search_term = f"%{search}%"
        query = query.filter(or_(Student.helli_code.ilike(search_term), Student.national_id.ilike(search_term), Student.student_mobile.ilike(search_term), func.concat(Student.first_name, ' ', Student.last_name).ilike(search_term)))
    students = query.paginate(page=page, per_page=15)
    return render_template('manage_students.html', students=students, search=search)
@app.route('/upload_students', methods=['POST'])
@login_required
@admin_required
def upload_students():
    if 'file' not in request.files or request.files['file'].filename == '':
        flash('هیچ فایلی انتخاب نشده است.', 'danger'); return redirect(url_for('manage_students'))
    file = request.files['file']
    if file and file.filename.endswith('.csv'):
        try:
            stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
            df = pd.read_csv(stream, dtype=str).fillna('')
            updated_count, added_count = 0, 0
            for index, row in df.iterrows():
                student = None
                if 'helli_code' in row and row['helli_code']: student = Student.query.filter_by(helli_code=row['helli_code']).first()
                if not student and 'national_id' in row and row['national_id']: student = Student.query.filter_by(national_id=row['national_id']).first()
                if not student and 'student_mobile' in row and row['student_mobile']: student = Student.query.filter_by(student_mobile=row['student_mobile']).first()
                if student:
                    student.national_id, student.first_name, student.last_name, student.gender, student.grade, student.province, student.student_mobile, student.parent_mobile, student.emergency_mobile = str(row.get('national_id')), row.get('first_name'), row.get('last_name'), row.get('gender'), row.get('grade'), row.get('province'), str(row.get('student_mobile')), str(row.get('parent_mobile')), str(row.get('emergency_mobile'))
                    updated_count += 1
                else:
                    new_student = Student(helli_code=str(row.get('helli_code')) if pd.notna(row.get('helli_code')) else None, national_id=str(row.get('national_id')) if pd.notna(row.get('national_id')) else None, first_name=row.get('first_name'), last_name=row.get('last_name'), gender=row.get('gender'), grade=row.get('grade'), province=row.get('province'), student_mobile=str(row.get('student_mobile')) if pd.notna(row.get('student_mobile')) else None, parent_mobile=str(row.get('parent_mobile')) if pd.notna(row.get('parent_mobile')) else None, emergency_mobile=str(row.get('emergency_mobile')) if pd.notna(row.get('emergency_mobile')) else None)
                    db.session.add(new_student)
                    added_count += 1
            db.session.commit()
            flash(f'فایل با موفقیت پردازش شد. {added_count} دانش‌آموز جدید و {updated_count} دانش‌آموز به‌روزرسانی شدند.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'خطا در پردازش فایل: {e}', 'danger')
        return redirect(url_for('manage_students'))
    flash('فرمت فایل باید CSV باشد.', 'warning')
    return redirect(url_for('manage_students'))
def create_default_departments():
    default_deps = ['کتابخوان', 'بازارهوشمند', 'آموزش', 'آزمون‌ها', 'عمومی']
    for dep_name in default_deps:
        if not Department.query.filter_by(name=dep_name).first():
            db.session.add(Department(name=dep_name))
    db.session.commit()
with app.app_context():
    db.create_all()
    create_default_departments()
