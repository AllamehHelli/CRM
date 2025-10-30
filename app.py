# ... (تمام import های قبلی) ...
import pandas as pd
from io import BytesIO
from flask import send_file
import jdatetime

# ... (تمام کدها تا قبل از مسیر index) ...
# (کلاس‌ها، توابع کمکی و مسیرهای لاگین/لاگوت بدون تغییر هستند)

@app.route('/')
@login_required
def index():
    query = Ticket.query
    
    # --- منطق جدید برای فیلتر کردن ---
    if current_user.role == 'admin':
        # ادمین می‌تواند فیلتر کند
        creators = User.query.all()
        
        # دریافت پارامترهای فیلتر از URL
        f_department = request.args.get('department')
        f_creator = request.args.get('creator')
        f_status = request.args.get('status')
        f_start_date = request.args.get('start_date')
        f_end_date = request.args.get('end_date')

        if f_department:
            query = query.filter(Ticket.department_id == f_department)
        if f_creator:
            query = query.filter(Ticket.creator_id == f_creator)
        if f_status:
            query = query.filter(Ticket.status == f_status)
        if f_start_date:
            start_date_gregorian = jdatetime.datetime.strptime(f_start_date, '%Y/%m/%d').togregorian()
            query = query.filter(Ticket.created_at >= start_date_gregorian)
        if f_end_date:
            end_date_gregorian = jdatetime.datetime.strptime(f_end_date, '%Y/%m/%d').togregorian().replace(hour=23, minute=59, second=59)
            query = query.filter(Ticket.created_at <= end_date_gregorian)
            
        tickets = query.order_by(Ticket.created_at.desc()).all()

    elif current_user.role == 'operator':
        creators = [] # اپراتور نیازی به این فیلتر ندارد
        tickets = Ticket.query.filter_by(department_id=current_user.department_id).order_by(Ticket.created_at.desc()).all()
    else: # counselor
        creators = []
        tickets = Ticket.query.filter_by(creator_id=current_user.id).order_by(Ticket.created_at.desc()).all()
        
    departments = Department.query.all()
    return render_template('index.html', tickets=tickets, departments=departments, creators=creators)


# --- مسیر جدید برای خروجی اکسل ---
@app.route('/export')
@login_required
@admin_required
def export_excel():
    query = Ticket.query
    # ... (تکرار دقیق منطق فیلتر از مسیر index) ...
    f_department = request.args.get('department')
    f_creator = request.args.get('creator')
    f_status = request.args.get('status')
    f_start_date = request.args.get('start_date')
    f_end_date = request.args.get('end_date')
    if f_department: query = query.filter(Ticket.department_id == f_department)
    if f_creator: query = query.filter(Ticket.creator_id == f_creator)
    if f_status: query = query.filter(Ticket.status == f_status)
    if f_start_date: query = query.filter(Ticket.created_at >= jdatetime.datetime.strptime(f_start_date, '%Y/%m/%d').togregorian())
    if f_end_date: query = query.filter(Ticket.created_at <= jdatetime.datetime.strptime(f_end_date, '%Y/%m/%d').togregorian().replace(hour=23, minute=59, second=59))
    
    tickets_to_export = query.order_by(Ticket.created_at.desc()).all()
    
    # تبدیل داده‌ها به فرمت مناسب برای pandas
    data = []
    for ticket in tickets_to_export:
        data.append({
            'شناسه': ticket.id,
            'عنوان': ticket.title,
            'حلی کد': ticket.student_code,
            'شرح مشکل': ticket.description,
            'وضعیت': get_status_display(ticket.status)[0],
            'بخش': ticket.department.name,
            'ایجاد کننده': f"{ticket.creator.first_name} {ticket.creator.last_name}",
            'تاریخ ایجاد (شمسی)': to_shamsi(ticket.created_at)
        })

    df = pd.DataFrame(data)
    
    # ساخت فایل اکسل در حافظه
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    df.to_excel(writer, index=False, sheet_name='گزارش تیکت‌ها')
    writer.close()
    output.seek(0)
    
    return send_file(output, download_name='report.xlsx', as_attachment=True)

# ... (تمام مسیرها و کدهای دیگر دقیقاً مانند قبل باقی می‌مانند) ...
