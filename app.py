import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# ساخت اپلیکیشن فلسک
app = Flask(__name__)

# خواندن آدرس پایگاه داده از متغیر محیطی که در Render تنظیم کردیم
db_url = os.environ.get("DATABASE_URL")

# تنظیمات اتصال به پایگاه داده
# یک تغییر کوچک در آدرس برای سازگاری کامل با SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ساخت نمونه SQLAlchemy و اتصال آن به اپلیکیشن فلسک
db = SQLAlchemy(app)

# --- تعریف مدل‌ (ساختار جدول پایگاه داده) ---
# این کلاس به SQLAlchemy می‌گوید که یک جدول به نام 'ticket' بسازد
class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True) # شناسه یکتای هر تیکت
    student_code = db.Column(db.String(20), nullable=False) # حلی کد دانش‌آموز
    title = db.Column(db.String(100), nullable=False) # عنوان مشکل
    description = db.Column(db.Text, nullable=False) # شرح کامل مشکل
    status = db.Column(db.String(20), default='New') # وضعیت تیکت: جدید، در حال بررسی، و غیره

    def __repr__(self):
        return f"<Ticket {self.id}: {self.title}>"

# --- مسیر اصلی برنامه (Route) ---
@app.route('/')
def index():
    # در آینده اینجا لیست تیکت‌ها را از دیتابیس می‌خوانیم و نمایش می‌دهیم
    return "<h1>اتصال به پایگاه داده با موفقیت برقرار شد!</h1><h2>مدل تیکت آماده است.</h2>"

# --- دستور ایجاد جداول در پایگاه داده ---
# این کد به محض اجرای برنامه، بررسی می‌کند که آیا جدول‌ها ساخته شده‌اند یا نه
# و اگر ساخته نشده باشند، آن‌ها را ایجاد می‌کند.
with app.app_context():
    db.create_all()
