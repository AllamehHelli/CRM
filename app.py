import os
# url_for را برای ساخت لینک‌های پویا اضافه می‌کنیم
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
db_url = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    tickets = db.relationship('Ticket', backref='department', lazy=True)

    def __repr__(self):
        return f"<Department {self.name}>"

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_code = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='New')
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)

    def __repr__(self):
        return f"<Ticket {self.id}: {self.title}>"

@app.route('/')
def index():
    tickets = Ticket.query.order_by(Ticket.id.desc()).all()
    departments = Department.query.all()
    return render_template('index.html', tickets=tickets, departments=departments)

@app.route('/create', methods=['POST'])
def create():
    student_code = request.form['student_code']
    title = request.form['title']
    description = request.form['description']
    department_id = request.form['department_id']
    
    new_ticket = Ticket(
        student_code=student_code,
        title=title,
        description=description,
        department_id=department_id
    )
    db.session.add(new_ticket)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/ticket/<int:ticket_id>')
def ticket_detail(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    return render_template('ticket_detail.html', ticket=ticket)

# --- مسیر جدید برای به‌روزرسانی وضعیت تیکت ---
@app.route('/ticket/<int:ticket_id>/update', methods=['POST'])
def update_status(ticket_id):
    # ۱. تیکت مورد نظر را پیدا می‌کنیم
    ticket_to_update = Ticket.query.get_or_404(ticket_id)
    # ۲. وضعیت جدید را از فرمی که ارسال شده می‌خوانیم
    new_status = request.form['status']
    # ۳. وضعیت تیکت را به‌روز می‌کنیم
    ticket_to_update.status = new_status
    # ۴. تغییرات را در پایگاه داده ذخیره می‌کنیم
    db.session.commit()
    # ۵. کاربر را به همان صفحه جزئیات تیکت بازمی‌گردانیم
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))


def create_default_departments():
    default_deps = ['کتابخوان', 'بازارهوشمند', 'آموزش', 'آزمون‌ها', 'عمومی']
    for dep_name in default_deps:
        existing_dep = Department.query.filter_by(name=dep_name).first()
        if not existing_dep:
            new_dep = Department(name=dep_name)
            db.session.add(new_dep)
    db.session.commit()

with app.app_context():
    db.create_all()
    create_default_departments()
