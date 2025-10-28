import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-key-that-should-be-changed')
db_url = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='counselor')

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

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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
    new_ticket = Ticket(student_code=student_code, title=title, description=description, department_id=department_id)
    db.session.add(new_ticket)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/ticket/<int:ticket_id>')
def ticket_detail(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    return render_template('ticket_detail.html', ticket=ticket)

@app.route('/ticket/<int:ticket_id>/update', methods=['POST'])
def update_status(ticket_id):
    ticket_to_update = Ticket.query.get_or_404(ticket_id)
    new_status = request.form['status']
    ticket_to_update.status = new_status
    db.session.commit()
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))

@app.route('/ticket/<int:ticket_id>/delete', methods=['POST'])
def delete_ticket(ticket_id):
    ticket_to_delete = Ticket.query.get_or_404(ticket_id)
    db.session.delete(ticket_to_delete)
    db.session.commit()
    return redirect(url_for('index'))

def create_default_departments():
    default_deps = ['کتابخوان', 'بازارهوشمند', 'آموزش', 'آزمون‌ها', 'عمومی']
    for dep_name in default_deps:
        # این خط در کد قبلی ناقص بود و حالا کامل شده است
        if not Department.query.filter_by(name=dep_name).first():
            db.session.add(Department(name=dep_name))
    db.session.commit()

with app.app_context():
    db.create_all()
    create_default_departments()
