import os
# request و redirect را برای مدیریت فرم اضافه می‌کنیم
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

# این مسیر، فرم را نمایش می‌دهد
@app.route('/')
def index():
    return render_template('index.html')

# --- مسیر جدید برای ذخیره کردن تیکت ---
# این مسیر فقط به درخواست‌های POST (ارسال فرم) پاسخ می‌دهد
@app.route('/create', methods=['POST'])
def create():
    # ۱. خواندن اطلاعات از فرم ارسال شده
    student_code = request.form['student_code']
    title = request.form['title']
    description = request.form['description']

    # ۲. ساخت یک نمونه جدید از کلاس Ticket با این اطلاعات
    new_ticket = Ticket(
        student_code=student_code,
        title=title,
        description=description
    )

    # ۳. اضافه کردن تیکت جدید به پایگاه داده و ذخیره آن
    db.session.add(new_ticket)
    db.session.commit()

    # ۴. انتقال کاربر به صفحه اصلی (برای ثبت تیکت بعدی)
    return redirect('/')


# این بخش برای ایجاد جدول‌ها بدون تغییر باقی می‌ماند
with app.app_context():
    db.create_all()
