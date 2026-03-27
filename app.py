from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, date, timedelta
from functools import wraps
from config import Config
from models import db, User, Event, Registration, Attendance, Notification
from forms import LoginForm, RegistrationForm, EventForm, NotificationSettingsForm
import threading
import time
import re
import socket

# Initialize Flask App
app = Flask(__name__)
app.config.from_object(Config)

# Initialize Extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==================== Admin Required Decorator ====================

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== Create Notification Function ====================

def create_notification(user_id, event_id, title, message, notification_type='push'):
    """Create a notification and respect user's email preferences"""
    notification = Notification(
        user_id=user_id,
        event_id=event_id,
        title=title,
        message=message,
        notification_type=notification_type
    )
    db.session.add(notification)
    
    user = User.query.get(user_id)
    if user and notification_type == 'email' and user.email_notifications:
        print(f"📧 Email would be sent to: {user.email}")
        print(f"   Subject: {title}")
        print(f"   Message: {message}")
    elif user and notification_type == 'email' and not user.email_notifications:
        print(f"📧 Email skipped for {user.email} (notifications disabled)")
    
    return notification

# ==================== AUTOMATIC REMINDER FUNCTION ====================

def send_automatic_reminders():
    with app.app_context():
        tomorrow = date.today() + timedelta(days=1)
        upcoming_events = Event.query.filter(Event.start_date == tomorrow).all()
        
        reminders_sent = 0
        for event in upcoming_events:
            registrations = Registration.query.filter_by(event_id=event.id).all()
            for reg in registrations:
                existing_reminder = Notification.query.filter_by(
                    user_id=reg.student_id,
                    event_id=event.id,
                    title='⏰ Event Reminder'
                ).first()
                
                if not existing_reminder:
                    create_notification(
                        reg.student_id, 
                        event.id, 
                        '⏰ Event Reminder', 
                        f'Reminder: "{event.title}" is TOMORROW at {event.venue}! Starts at {event.start_time.strftime("%I:%M %p")}. Don\'t miss it!',
                        'email'
                    )
                    reminders_sent += 1
        
        if reminders_sent > 0:
            db.session.commit()
            print(f"✅ Auto-sent {reminders_sent} reminders for tomorrow's events")

def reminder_scheduler():
    last_run_date = None
    while True:
        try:
            current_date = date.today()
            if last_run_date != current_date:
                send_automatic_reminders()
                last_run_date = current_date
            time.sleep(3600)
        except Exception as e:
            print(f"Reminder scheduler error: {e}")
            time.sleep(3600)

reminder_thread = threading.Thread(target=reminder_scheduler, daemon=True)
reminder_thread.start()
print("✅ Automatic reminder system started!")

# ==================== Public Routes ====================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    today = date.today()
    upcoming_events = Event.query.filter(Event.start_date >= today).order_by(Event.start_date).limit(6).all()
    return render_template('index.html', upcoming_events=upcoming_events)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash(f'Welcome back, {user.full_name}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user:
            flash('Username already taken.', 'danger')
            return render_template('register.html', form=form)
        
        existing_email = User.query.filter_by(email=form.email.data).first()
        if existing_email:
            flash('Email already registered.', 'danger')
            return render_template('register.html', form=form)
        
        user = User(
            username=form.username.data,
            email=form.email.data,
            full_name=form.full_name.data,
            department=form.department.data,
            role=form.role.data,
            email_notifications=form.email_notifications.data
        )
        user.set_password(form.password.data)
        
        try:
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Registration failed: {str(e)}', 'danger')
    return render_template('register.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# ==================== Dashboard Routes ====================

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_faculty():
        events = Event.query.filter_by(created_by=current_user.id).order_by(Event.start_date).all()
        upcoming_count = Event.query.filter(Event.start_date >= date.today(), Event.created_by == current_user.id).count()
        total_participants = 0
        for event in events:
            total_participants += Registration.query.filter_by(event_id=event.id).count()
        return render_template('dashboard_faculty.html', events=events, upcoming_count=upcoming_count, total_participants=total_participants, events_count=len(events))
    else:
        registered_events = Registration.query.filter_by(student_id=current_user.id).all()
        registered_event_ids = [reg.event_id for reg in registered_events]
        upcoming_events = Event.query.filter(Event.start_date >= date.today(), Event.id.notin_(registered_event_ids)).order_by(Event.start_date).limit(10).all()
        my_events = Event.query.filter(Event.id.in_(registered_event_ids)).order_by(Event.start_date).all()
        notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
        return render_template('dashboard_student.html', upcoming_events=upcoming_events, my_events=my_events, notifications=notifications)

# ==================== Event Routes ====================

@app.route('/events')
@login_required
def events():
    event_type = request.args.get('type', '')
    status = request.args.get('status', '')
    query = Event.query
    if event_type:
        query = query.filter_by(event_type=event_type)
    today = date.today()
    if status == 'upcoming':
        query = query.filter(Event.start_date >= today)
    elif status == 'completed':
        query = query.filter(Event.start_date < today)
    events = query.order_by(Event.start_date).all()
    registered_event_ids = []
    if current_user.is_student():
        registrations = Registration.query.filter_by(student_id=current_user.id).all()
        registered_event_ids = [reg.event_id for reg in registrations]
    return render_template('events/list.html', events=events, registered_event_ids=registered_event_ids, current_type=event_type, current_status=status)

@app.route('/events/create', methods=['GET', 'POST'])
@login_required
def create_event():
    if not current_user.is_faculty():
        flash('Only faculty members can create events.', 'danger')
        return redirect(url_for('dashboard'))
    form = EventForm()
    if form.validate_on_submit():
        if form.start_date.data < date.today():
            flash('Start date cannot be in the past.', 'danger')
            return render_template('events/create.html', form=form)
        if form.end_date.data and form.end_date.data < form.start_date.data:
            flash('End date cannot be before start date.', 'danger')
            return render_template('events/create.html', form=form)
        if form.start_date.data == form.end_date.data:
            if form.end_time.data <= form.start_time.data:
                flash('End time must be after start time.', 'danger')
                return render_template('events/create.html', form=form)
        
        event = Event(
            title=form.title.data, description=form.description.data, event_type=form.event_type.data,
            venue=form.venue.data, start_date=form.start_date.data, end_date=form.end_date.data,
            start_time=form.start_time.data, end_time=form.end_time.data,
            max_participants=form.max_participants.data, created_by=current_user.id
        )
        try:
            db.session.add(event)
            db.session.commit()
            students = User.query.filter_by(role='student').all()
            for student in students:
                create_notification(student.id, event.id, '🎉 New Event Created!', f'New event "{event.title}" on {event.start_date.strftime("%B %d, %Y")} at {event.venue}. Register now!', 'push')
            db.session.commit()
            flash(f'Event "{event.title}" created successfully!', 'success')
            return redirect(url_for('events'))
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to create event: {str(e)}', 'danger')
    return render_template('events/create.html', form=form)

@app.route('/events/<int:event_id>')
@login_required
def event_details(event_id):
    event = Event.query.get_or_404(event_id)
    is_registered = False
    if current_user.is_student():
        registration = Registration.query.filter_by(event_id=event.id, student_id=current_user.id).first()
        is_registered = registration is not None
    registered_count = event.get_registration_count()
    registered_students = []
    if current_user.is_faculty() and event.created_by == current_user.id:
        registrations = Registration.query.filter_by(event_id=event.id).all()
        for reg in registrations:
            student = User.query.get(reg.student_id)
            attendance = Attendance.query.filter_by(event_id=event.id, student_id=student.id).first()
            registered_students.append({'student': student, 'attended': attendance.attended if attendance else False})
    return render_template('events/details.html', event=event, is_registered=is_registered, registered_count=registered_count, registered_students=registered_students)

@app.route('/events/<int:event_id>/register')
@login_required
def register_event(event_id):
    if not current_user.is_student():
        flash('Only students can register for events.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))
    event = Event.query.get_or_404(event_id)
    if event.start_date < date.today():
        flash('Cannot register for past events.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))
    existing = Registration.query.filter_by(event_id=event.id, student_id=current_user.id).first()
    if existing:
        flash('You are already registered.', 'warning')
        return redirect(url_for('event_details', event_id=event_id))
    if event.is_full():
        flash('This event is full.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))
    registration = Registration(event_id=event.id, student_id=current_user.id)
    create_notification(current_user.id, event.id, '✅ Registration Confirmed!', f'You registered for "{event.title}" on {event.start_date.strftime("%B %d, %Y")}.', 'email')
    create_notification(event.created_by, event.id, '📋 New Registration', f'Student {current_user.full_name} registered for "{event.title}"', 'push')
    try:
        db.session.add(registration)
        db.session.commit()
        flash(f'Successfully registered for "{event.title}"!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to register: {str(e)}', 'danger')
    return redirect(url_for('event_details', event_id=event_id))

@app.route('/events/<int:event_id>/cancel')
@login_required
def cancel_registration(event_id):
    if not current_user.is_student():
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    registration = Registration.query.filter_by(event_id=event_id, student_id=current_user.id).first_or_404()
    event = Event.query.get(event_id)
    if event.start_date < date.today():
        flash('Cannot cancel past events.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))
    create_notification(event.created_by, event.id, '❌ Registration Cancelled', f'Student {current_user.full_name} cancelled registration for "{event.title}"', 'push')
    try:
        db.session.delete(registration)
        db.session.commit()
        flash(f'Registration for "{event.title}" cancelled.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to cancel: {str(e)}', 'danger')
    return redirect(url_for('events'))

# ==================== Attendance Routes ====================

@app.route('/attendance/<int:event_id>/mark', methods=['GET', 'POST'])
@login_required
def mark_attendance(event_id):
    if not current_user.is_faculty():
        flash('Only faculty can mark attendance.', 'danger')
        return redirect(url_for('dashboard'))
    event = Event.query.get_or_404(event_id)
    if event.created_by != current_user.id and not current_user.is_admin():
        flash('You can only mark attendance for your events.', 'danger')
        return redirect(url_for('dashboard'))
    if event.start_date > date.today():
        flash('Cannot mark future events.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))
    registrations = Registration.query.filter_by(event_id=event.id).all()
    if not registrations:
        flash('No students registered.', 'warning')
        return redirect(url_for('event_details', event_id=event_id))
    if request.method == 'POST':
        for reg in registrations:
            attended = request.form.get(f'attendance_{reg.student_id}') == 'on'
            attendance = Attendance.query.filter_by(event_id=event.id, student_id=reg.student_id).first()
            if attendance:
                attendance.attended = attended
                attendance.marked_by = current_user.id
                attendance.marked_at = datetime.now()
            else:
                attendance = Attendance(event_id=event.id, student_id=reg.student_id, attended=attended, marked_by=current_user.id)
                db.session.add(attendance)
            if attended:
                create_notification(reg.student_id, event.id, '✅ Attendance Marked', f'Your attendance for "{event.title}" marked as PRESENT', 'email')
            else:
                create_notification(reg.student_id, event.id, '📝 Attendance Marked', f'Your attendance for "{event.title}" marked as ABSENT', 'email')
        try:
            db.session.commit()
            flash('Attendance saved!', 'success')
            return redirect(url_for('event_details', event_id=event.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Failed: {str(e)}', 'danger')
    attendance_records = {}
    for reg in registrations:
        attendance = Attendance.query.filter_by(event_id=event.id, student_id=reg.student_id).first()
        attendance_records[reg.student_id] = attendance.attended if attendance else False
    return render_template('attendance/mark.html', event=event, registrations=registrations, attendance_records=attendance_records)

@app.route('/send_reminders_manual')
@login_required
@admin_required
def send_reminders_manual():
    send_automatic_reminders()
    flash('Reminders sent!', 'success')
    return redirect(url_for('admin_dashboard'))

# ==================== Notification Routes ====================

@app.route('/notifications')
@login_required
def notifications():
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    for notif in notifications:
        notif.is_read = True
    try:
        db.session.commit()
    except:
        db.session.rollback()
    return render_template('notifications.html', notifications=notifications)

# ==================== Profile Routes ====================

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = NotificationSettingsForm()
    if form.validate_on_submit():
        current_user.email_notifications = form.email_notifications.data
        current_user.push_notifications = form.push_notifications.data
        db.session.commit()
        flash('Notification settings updated!', 'success')
        return redirect(url_for('profile'))
    form.email_notifications.data = current_user.email_notifications
    form.push_notifications.data = current_user.push_notifications
    if current_user.is_student():
        my_events_count = Registration.query.filter_by(student_id=current_user.id).count()
        registrations = Registration.query.filter_by(student_id=current_user.id).all()
        total_registrations = len(registrations)
        attended_count = 0
        for reg in registrations:
            attendance = Attendance.query.filter_by(event_id=reg.event_id, student_id=current_user.id, attended=True).first()
            if attendance:
                attended_count += 1
        attendance_percentage = (attended_count / total_registrations * 100) if total_registrations > 0 else 0
    else:
        my_events_count = Event.query.filter_by(created_by=current_user.id).count()
        attendance_percentage = 0
    return render_template('profile.html', my_events_count=my_events_count, attendance_percentage=int(attendance_percentage), form=form)

# ==================== Admin Routes ====================

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_events = Event.query.count()
    total_registrations = Registration.query.count()
    total_attendance = Attendance.query.filter_by(attended=True).count()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_events = Event.query.order_by(Event.created_at.desc()).limit(5).all()
    return render_template('admin/dashboard.html', total_users=total_users, total_events=total_events, total_registrations=total_registrations, total_attendance=total_attendance, recent_users=recent_users, recent_events=recent_events)

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/user/<int:user_id>/role', methods=['POST'])
@login_required
@admin_required
def admin_change_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    if new_role in ['admin', 'faculty', 'student']:
        user.role = new_role
        db.session.commit()
        flash(f'User {user.username} role changed to {new_role}', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot delete yourself!', 'danger')
    else:
        Registration.query.filter_by(student_id=user.id).delete()
        Notification.query.filter_by(user_id=user.id).delete()
        Attendance.query.filter_by(student_id=user.id).delete()
        Event.query.filter_by(created_by=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.username} deleted', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/stats')
@login_required
@admin_required
def admin_stats():
    users_count = User.query.count()
    faculty_count = User.query.filter_by(role='faculty').count()
    student_count = User.query.filter_by(role='student').count()
    admin_count = User.query.filter_by(role='admin').count()
    events_count = Event.query.count()
    upcoming_events = Event.query.filter(Event.start_date >= date.today()).count()
    completed_events = Event.query.filter(Event.start_date < date.today()).count()
    registrations_count = Registration.query.count()
    attendance_count = Attendance.query.filter_by(attended=True).count()
    return render_template('admin/stats.html', users_count=users_count, faculty_count=faculty_count, student_count=student_count, admin_count=admin_count, events_count=events_count, upcoming_events=upcoming_events, completed_events=completed_events, registrations_count=registrations_count, attendance_count=attendance_count)

# ==================== Error Handlers ====================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# ==================== Run Application ====================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Database tables created/verified!")
    print("\n✅ CampusLink is running!")
    print("📍 Access at: http://127.0.0.1:5000")
    print("=" * 50)
    app.run(debug=True, host='127.0.0.1', port=5000)