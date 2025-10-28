import os
from flask import Flask, render_template  # render_template را اضافه کردیم
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

# --- مسیر اصلی برنامه (Route) ---
# این تابع را تغییر دادیم
@app.route('/')
def index():
    # به جای متن ساده، حالا فایل index.html را به کاربر نمایش می‌دهیم
    return render_template('index.html')

# این بخش برای ایجاد جدول‌ها سر جای خودش باقی می‌ماند
with app.app_context():
    db.create_all()
