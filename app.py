import os
from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
db_url = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- مدل جدید برای بخش‌ها ---
class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    # این خط به ما اجازه می‌دهد تا به لیست تیکت‌های هر بخش دسترسی داشته باشیم
    tickets = db.relationship('Ticket', backref='department', lazy=True)

    def __repr__(self):
        return f"<Department {self.name}>"

# --- مدل تیکت به‌روز شده ---
class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_code = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='New')
    # این خط تیکت را به یک بخش متصل می‌کند
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)

    def __repr__(self):
        return f"<Ticket {self.id}: {self.title}>"

# --- تابع نمایش فرم و لیست تیکت‌ها (تغییر کرده) ---
@app.route('/')
def index():
    tickets = Ticket.query.order_by(Ticket.id.desc()).all()
    # حالا لیست بخش‌ها را هم از دیتابیس می‌خوانیم و به صفحه ارسال می‌کنیم
    departments = Department.query.all()
    return render_template('index.html', tickets=tickets, departments=departments)

# --- تابع ثبت تیکت (تغییر کرده) ---
@app.route('/create', methods=['POST'])
def create():
    student_code = request.form['student_code']
    title = request.form['title']
    description = request.form['description']
    # ID بخش انتخاب شده را از فرم می‌خوانیم
    department_id = request.form['department_id']
    
    new_ticket = Ticket(
        student_code=student_code,
        title=title,
        description=description,
        department_id=department_id # و اینجا ذخیره می‌کنیم
    )
    db.session.add(new_ticket)
    db.session.commit()
    return redirect('/')

# --- تابع برای ساخت بخش‌های پیش‌فرض ---
def create_default_departments():
    # لیست بخش‌های اولیه شما
    default_deps = ['کتابخوان', 'بازارهوشمند', 'آموزش', 'آزمون‌ها', 'عمومی']
    for dep_name in default_deps:
        # بررسی می‌کنیم که آیا این بخش قبلاً ساخته شده یا نه
        existing_dep = Department.query.filter_by(name=dep_name).first()
        if not existing_dep:
            new_dep = Department(name=dep_name)
            db.session.add(new_dep)
    db.session.commit()

# --- ایجاد جداول و بخش‌های پیش‌فرض ---
with app.app_context():
    db.create_all()
    create_default_departments()
