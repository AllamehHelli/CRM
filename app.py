import os
from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
db_url = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_code = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='New')

    def __repr__(self):
        return f"<Ticket {self.id}: {self.title}>"

# --- تغییر مهم در این تابع اتفاق افتاده است ---
@app.route('/')
def index():
    # ۱. خواندن تمام تیکت‌ها از پایگاه داده و مرتب کردن آن‌ها بر اساس ID به صورت نزولی
    tickets = Ticket.query.order_by(Ticket.id.desc()).all()
    # ۲. ارسال لیست تیکت‌ها به فایل HTML
    return render_template('index.html', tickets=tickets)

@app.route('/create', methods=['POST'])
def create():
    student_code = request.form['student_code']
    title = request.form['title']
    description = request.form['description']
    new_ticket = Ticket(
        student_code=student_code,
        title=title,
        description=description
    )
    db.session.add(new_ticket)
    db.session.commit()
    return redirect('/')

with app.app_context():
    db.create_all()
