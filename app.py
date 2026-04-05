from flask import (Flask, render_template, redirect, url_for, flash,
                   request, jsonify, send_from_directory)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, date, timedelta
from functools import wraps
from config import Config
from models import (db, User, Event, Registration, Attendance, Notification,
                    EventGroup, GroupRegistration, EventOrganizer,
                    CoordinatorApplication, BRANCH_CHOICES, YEAR_CHOICES)
from forms import (LoginForm, RegistrationForm, EventForm, NotificationSettingsForm,
                   GroupRegistrationForm, CoordinatorApplicationForm, ReceiptUploadForm)
from email_utils import (send_verification_email, send_coordinator_application_email,
                         send_coordinator_decision_email, send_event_update_email,
                         send_payment_receipt_email, send_payment_approved_email,
                         send_payment_rejected_email)
import threading
import time
import secrets
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config.from_object(Config)

# Upload folders
QR_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'qr_codes')
RECEIPT_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'receipts')
os.makedirs(QR_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RECEIPT_UPLOAD_FOLDER, exist_ok=True)

ALLOWED_QR_EXT = {'jpg', 'jpeg', 'png'}
ALLOWED_RECEIPT_EXT = {'jpg', 'jpeg', 'png', 'pdf'}
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─────────────────────────── FILE HELPERS ───────────────────────────

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set


def save_upload(file_obj, folder, allowed_set, prefix='file'):
    """Save an uploaded file securely. Returns relative path or None."""
    if not file_obj or not file_obj.filename:
        return None
    if not allowed_file(file_obj.filename, allowed_set):
        return None
    file_obj.seek(0, 2)
    size = file_obj.tell()
    file_obj.seek(0)
    if size > MAX_FILE_BYTES:
        return None
    ext = file_obj.filename.rsplit('.', 1)[1].lower()
    unique_name = f"{prefix}_{secrets.token_hex(10)}.{ext}"
    save_path = os.path.join(folder, unique_name)
    file_obj.save(save_path)
    return unique_name  # store only filename, build URL at render time


# ─────────────────────────── DECORATORS ───────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def can_create_events(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_create_events():
            flash('You do not have permission to create events.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# ─────────────────────────── HELPERS ───────────────────────────

def create_notification(user_id, event_id, title, message, notification_type='push'):
    notification = Notification(
        user_id=user_id, event_id=event_id,
        title=title, message=message,
        notification_type=notification_type
    )
    db.session.add(notification)
    return notification


def notify_eligible_students(event, title, message):
    students = User.query.filter(User.role.in_(['student', 'student_coordinator'])).all()
    count = 0
    for student in students:
        if event.is_user_eligible(student):
            create_notification(student.id, event.id, title, message, 'push')
            count += 1
    return count


def notify_registered_students(event, title, message):
    registrations = Registration.query.filter_by(event_id=event.id).all()
    for reg in registrations:
        create_notification(reg.student_id, event.id, title, message, 'push')


def get_event_changes(old_event, form):
    changes = []
    field_map = {
        'title': ('Title', old_event.title, form.title.data),
        'venue': ('Venue', old_event.venue, form.venue.data),
        'start_date': ('Start Date', str(old_event.start_date), str(form.start_date.data)),
        'end_date': ('End Date', str(old_event.end_date), str(form.end_date.data)),
        'start_time': ('Start Time', str(old_event.start_time), str(form.start_time.data)),
        'end_time': ('End Time', str(old_event.end_time), str(form.end_time.data)),
        'max_participants': ('Max Participants', str(old_event.max_participants), str(form.max_participants.data)),
        'description': ('Description', (old_event.description or '')[:60], (form.description.data or '')[:60]),
    }
    for key, (label, old_val, new_val) in field_map.items():
        if str(old_val) != str(new_val):
            changes.append(f"{label} changed from '{old_val}' to '{new_val}'")
    new_college = form.eligible_college.data
    new_branch = ','.join(form.eligible_branch.data) if form.eligible_branch.data else 'all'
    new_year = ','.join(form.eligible_year.data) if form.eligible_year.data else 'all'
    if old_event.eligible_college != new_college:
        changes.append(f"Eligible college changed to '{new_college}'")
    if old_event.eligible_branch != new_branch:
        changes.append("Eligible branches updated")
    if old_event.eligible_year != new_year:
        changes.append("Eligible years updated")
    # Payment changes
    new_requires = form.requires_payment.data
    if old_event.requires_payment != new_requires:
        changes.append(f"Payment requirement {'added' if new_requires else 'removed'}")
    if new_requires and form.payment_amount.data:
        if str(old_event.payment_amount) != str(form.payment_amount.data):
            changes.append(f"Payment amount changed to ₹{form.payment_amount.data}")
    return changes


def process_organizers(event, form):
    errors = []
    creator = User.query.get(event.created_by)
    fc_username = (form.faculty_coordinator_username.data or '').strip()

    if creator and creator.is_student_coordinator():
        if not fc_username:
            errors.append('A Faculty Coordinator is required when a Student Coordinator creates an event.')
            return errors
        fc_user = User.query.filter_by(username=fc_username).first()
        if not fc_user:
            errors.append(f'Faculty coordinator "@{fc_username}" not found.')
            return errors
        if not fc_user.is_faculty():
            errors.append(f'"{fc_username}" is not a faculty member.')
            return errors
        existing = EventOrganizer.query.filter_by(event_id=event.id, user_id=fc_user.id).first()
        if not existing:
            db.session.add(EventOrganizer(event_id=event.id, user_id=fc_user.id, role='faculty_coordinator'))
    elif fc_username:
        fc_user = User.query.filter_by(username=fc_username).first()
        if fc_user and fc_user.is_faculty():
            existing = EventOrganizer.query.filter_by(event_id=event.id, user_id=fc_user.id).first()
            if not existing:
                db.session.add(EventOrganizer(event_id=event.id, user_id=fc_user.id, role='faculty_coordinator'))

    co_usernames = [u.strip() for u in (form.co_organizer_usernames.data or '').split(',') if u.strip()]
    for uname in co_usernames:
        co_user = User.query.filter_by(username=uname).first()
        if not co_user:
            errors.append(f'Co-organizer "@{uname}" not found.')
            continue
        if not co_user.can_create_events():
            errors.append(f'"{uname}" is not eligible to be a co-organizer.')
            continue
        existing = EventOrganizer.query.filter_by(event_id=event.id, user_id=co_user.id).first()
        if not existing:
            db.session.add(EventOrganizer(event_id=event.id, user_id=co_user.id, role='co_organizer'))
    return errors


def set_payment_status_for_registration(registration, event):
    """Set initial payment status based on whether event requires payment."""
    if event.requires_payment:
        registration.payment_status = 'pending'
        registration.status = 'pending'
    else:
        registration.payment_status = 'not_required'
        registration.status = 'confirmed'


# ─────────────────────────── REMINDER SCHEDULER ───────────────────────────

def send_automatic_reminders():
    with app.app_context():
        tomorrow = date.today() + timedelta(days=1)
        upcoming_events = Event.query.filter(Event.start_date == tomorrow).all()
        reminders_sent = 0
        for event in upcoming_events:
            # Only remind confirmed registrations
            registrations = Registration.query.filter_by(
                event_id=event.id, status='confirmed').all()
            for reg in registrations:
                existing = Notification.query.filter_by(
                    user_id=reg.student_id, event_id=event.id, title='⏰ Event Reminder').first()
                if not existing:
                    create_notification(
                        reg.student_id, event.id, '⏰ Event Reminder',
                        f'Reminder: "{event.title}" is TOMORROW at {event.venue}! '
                        f'Starts at {event.start_time.strftime("%I:%M %p")}.',
                        'email'
                    )
                    reminders_sent += 1
        if reminders_sent > 0:
            db.session.commit()
            print(f"✅ Auto-sent {reminders_sent} reminders")


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


# ─────────────────────────── SERVE UPLOADS ───────────────────────────

@app.route('/uploads/qr_codes/<filename>')
@login_required
def serve_qr(filename):
    return send_from_directory(QR_UPLOAD_FOLDER, filename)


@app.route('/uploads/receipts/<filename>')
@login_required
def serve_receipt(filename):
    # Only organizers or the owner can view receipts
    return send_from_directory(RECEIPT_UPLOAD_FOLDER, filename)


# ─────────────────────────── AUTH ROUTES ───────────────────────────

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
            if not user.email_verified:
                flash('Please verify your email before logging in.', 'warning')
                return render_template('login.html', form=form, unverified_email=user.email)
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
        if form.college.data == 'MGIT':
            college = 'MGIT'
            college_name = 'MGIT'
            branch = form.branch.data
        else:
            college = 'other'
            college_name = form.college_name.data
            branch = form.branch_other.data.upper()

        user = User(
            username=form.username.data, email=form.email.data,
            roll_no=form.roll_no.data, full_name=form.full_name.data,
            college=college, college_name=college_name,
            branch=branch, year=form.year.data,
            role=form.role.data, email_notifications=form.email_notifications.data,
            email_verified=False
        )
        user.set_password(form.password.data)
        verification_token = user.generate_verification_token()
        try:
            db.session.add(user)
            db.session.commit()
            send_verification_email(user.email, user.full_name, verification_token)
            flash('Registration successful! Please verify your email before logging in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Registration failed: {str(e)}', 'danger')
    return render_template('register.html', form=form)


@app.route('/verify/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    if not user:
        flash('Invalid or expired verification link.', 'danger')
        return redirect(url_for('login'))
    if user.token_created_at and datetime.utcnow() - user.token_created_at > timedelta(hours=24):
        flash('Verification link has expired.', 'danger')
        return redirect(url_for('login'))
    if user.email_verified:
        flash('Email already verified.', 'info')
        return redirect(url_for('login'))
    user.email_verified = True
    user.verification_token = None
    try:
        db.session.commit()
        flash('Email verified successfully! You can now login.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Verification failed: {str(e)}', 'danger')
    return redirect(url_for('login'))


@app.route('/resend_verification', methods=['GET', 'POST'])
def resend_verification():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('No account found with this email.', 'danger')
            return redirect(url_for('login'))
        if user.email_verified:
            flash('Email already verified.', 'info')
            return redirect(url_for('login'))
        verification_token = user.generate_verification_token()
        user.token_created_at = datetime.utcnow()
        try:
            db.session.commit()
            send_verification_email(user.email, user.full_name, verification_token)
            flash('A new verification link has been sent.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Failed: {str(e)}', 'danger')
        return redirect(url_for('login'))
    return render_template('resend_verification.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# ─────────────────────────── DASHBOARD ───────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_faculty():
        events = Event.query.filter_by(created_by=current_user.id).order_by(Event.start_date).all()
        co_events_ids = [o.event_id for o in EventOrganizer.query.filter_by(user_id=current_user.id).all()]
        co_events = Event.query.filter(Event.id.in_(co_events_ids),
                                       Event.created_by != current_user.id).all()
        upcoming_count = sum(1 for e in events + co_events if e.start_date >= date.today())
        total_participants = sum(e.get_registration_count() for e in events)
        return render_template('dashboard_faculty.html', events=events, co_events=co_events,
                               upcoming_count=upcoming_count, total_participants=total_participants,
                               events_count=len(events))

    elif current_user.is_student_coordinator():
        events = Event.query.filter_by(created_by=current_user.id).order_by(Event.start_date).all()
        co_events_ids = [o.event_id for o in EventOrganizer.query.filter_by(user_id=current_user.id).all()]
        co_events = Event.query.filter(Event.id.in_(co_events_ids),
                                       Event.created_by != current_user.id).all()
        upcoming_count = sum(1 for e in events + co_events if e.start_date >= date.today())
        total_participants = sum(e.get_registration_count() for e in events)
        return render_template('dashboard_coordinator.html', events=events, co_events=co_events,
                               upcoming_count=upcoming_count, total_participants=total_participants,
                               events_count=len(events))
    else:
        registered_events = Registration.query.filter_by(student_id=current_user.id).all()
        registered_event_ids = [reg.event_id for reg in registered_events]
        all_events = Event.query.filter(Event.start_date >= date.today()).order_by(Event.start_date).all()
        upcoming_events = [e for e in all_events
                           if e.id not in registered_event_ids and e.is_user_eligible(current_user)][:10]
        my_events = Event.query.filter(Event.id.in_(registered_event_ids)).order_by(Event.start_date).all()
        notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False)\
            .order_by(Notification.created_at.desc()).limit(5).all()
        pending_app = CoordinatorApplication.query.filter_by(
            user_id=current_user.id, status='pending').first()
        # Pending payment registrations for student
        pending_payments = Registration.query.filter_by(
            student_id=current_user.id, payment_status='pending').all()
        rejected_payments = Registration.query.filter_by(
            student_id=current_user.id, payment_status='rejected').all()
        return render_template('dashboard_student.html',
                               upcoming_events=upcoming_events, my_events=my_events,
                               notifications=notifications,
                               pending_coordinator_app=pending_app,
                               pending_payments=pending_payments,
                               rejected_payments=rejected_payments,
                               registered_events=registered_events)


# ─────────────────────────── COORDINATOR APPLICATION ───────────────────────────

@app.route('/apply_coordinator', methods=['GET', 'POST'])
@login_required
def apply_coordinator():
    if not current_user.is_student():
        flash('Only students can apply.', 'danger')
        return redirect(url_for('dashboard'))
    existing = CoordinatorApplication.query.filter_by(user_id=current_user.id, status='pending').first()
    if existing:
        flash('You already have a pending application.', 'warning')
        return redirect(url_for('dashboard'))
    form = CoordinatorApplicationForm()
    if form.validate_on_submit():
        app_record = CoordinatorApplication(
            user_id=current_user.id, status='pending', reason=form.reason.data)
        current_user.coordinator_status = 'pending'
        try:
            db.session.add(app_record)
            db.session.commit()
            admins = User.query.filter_by(role='admin').all()
            server_name = app.config.get('SERVER_NAME', '127.0.0.1:5000')
            review_url = f"http://{server_name}/admin/coordinator_applications"
            for admin in admins:
                send_coordinator_application_email(
                    admin.email, current_user.full_name,
                    current_user.username, form.reason.data, review_url)
                create_notification(admin.id, None, '📋 New Coordinator Application',
                                    f'{current_user.full_name} applied to become a Student Coordinator.', 'push')
            db.session.commit()
            flash('Application submitted! Admin will review it shortly.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Failed: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
    return render_template('apply_coordinator.html', form=form)


# ─────────────────────────── EVENTS ───────────────────────────

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
    all_events = query.order_by(Event.start_date).all()

    if current_user.is_student() or current_user.is_student_coordinator():
        filtered_events = [e for e in all_events if e.is_user_eligible(current_user)]
    else:
        filtered_events = all_events

    registered_event_ids = []
    if current_user.is_student() or current_user.is_student_coordinator():
        registrations = Registration.query.filter_by(student_id=current_user.id).all()
        registered_event_ids = [reg.event_id for reg in registrations]

    return render_template('events/list.html', events=filtered_events,
                           registered_event_ids=registered_event_ids,
                           current_type=event_type, current_status=status)


@app.route('/events/create', methods=['GET', 'POST'])
@login_required
@can_create_events
def create_event():
    form = EventForm()
    if form.validate_on_submit():
        if form.start_date.data < date.today():
            flash('Start date cannot be in the past.', 'danger')
            return render_template('events/create.html', form=form)
        if form.end_date.data and form.end_date.data < form.start_date.data:
            flash('End date cannot be before start date.', 'danger')
            return render_template('events/create.html', form=form)
        if form.start_date.data == (form.end_date.data or form.start_date.data):
            if form.end_time.data <= form.start_time.data:
                flash('End time must be after start time.', 'danger')
                return render_template('events/create.html', form=form)

        # Validate payment: if required, QR must be uploaded
        if form.requires_payment.data:
            if not form.payment_qr.data or not form.payment_qr.data.filename:
                flash('Please upload a QR code image for payment.', 'danger')
                return render_template('events/create.html', form=form)

        group_size = 1
        participation_type = form.participation_type.data
        if participation_type == 'group':
            group_size = int(form.group_size.data)

        eligible_branch = ','.join(form.eligible_branch.data) if form.eligible_branch.data else 'all'
        eligible_year = ','.join(form.eligible_year.data) if form.eligible_year.data else 'all'

        # Save QR code if provided
        qr_filename = None
        if form.requires_payment.data and form.payment_qr.data:
            qr_filename = save_upload(form.payment_qr.data, QR_UPLOAD_FOLDER,
                                      ALLOWED_QR_EXT, prefix='qr')
            if not qr_filename:
                flash('Invalid QR file. Use JPG or PNG under 5MB.', 'danger')
                return render_template('events/create.html', form=form)

        event = Event(
            title=form.title.data, description=form.description.data,
            event_type=form.event_type.data, participation_type=participation_type,
            group_size=group_size, venue=form.venue.data,
            start_date=form.start_date.data, end_date=form.end_date.data,
            start_time=form.start_time.data, end_time=form.end_time.data,
            max_participants=form.max_participants.data, created_by=current_user.id,
            eligible_college=form.eligible_college.data,
            eligible_branch=eligible_branch, eligible_year=eligible_year,
            requires_payment=form.requires_payment.data,
            payment_amount=form.payment_amount.data if form.requires_payment.data else None,
            payment_qr_path=qr_filename,
            payment_note=form.payment_note.data if form.requires_payment.data else None,
        )

        try:
            db.session.add(event)
            db.session.flush()
            db.session.add(EventOrganizer(event_id=event.id, user_id=current_user.id, role='creator'))
            if participation_type == 'group':
                db.session.add(EventGroup(event_id=event.id, group_size=group_size))

            errors = process_organizers(event, form)
            if errors:
                db.session.rollback()
                for err in errors:
                    flash(err, 'danger')
                return render_template('events/create.html', form=form)

            db.session.commit()
            count = notify_eligible_students(
                event, '🎉 New Event!',
                f'New {participation_type} event "{event.title}" on '
                f'{event.start_date.strftime("%B %d, %Y")} at {event.venue}.'
                + (' Payment required: ₹' + str(event.payment_amount) if event.requires_payment else '')
            )
            db.session.commit()
            flash(f'Event "{event.title}" created! {count} eligible students notified.', 'success')
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
    group_members = []
    my_registration = None

    if current_user.is_student() or current_user.is_student_coordinator():
        my_registration = Registration.query.filter_by(
            event_id=event.id, student_id=current_user.id).first()
        is_registered = my_registration is not None
        if event.participation_type == 'group' and is_registered and current_user.roll_no:
            group_reg = GroupRegistration.query.filter_by(
                event_id=event.id, member_roll_no=current_user.roll_no).first()
            if group_reg:
                group_members = GroupRegistration.query.filter_by(
                    event_id=event.id, group_leader_id=group_reg.group_leader_id).all()

    registered_count = event.get_registration_count()
    registered_students = []
    is_event_organizer = event.is_organizer(current_user) or current_user.is_admin()

    if is_event_organizer:
        if event.participation_type == 'group':
            groups = GroupRegistration.query.filter_by(event_id=event.id).all()
            groups_dict = {}
            for gr in groups:
                if gr.group_leader_id not in groups_dict:
                    groups_dict[gr.group_leader_id] = {
                        'leader': User.query.get(gr.group_leader_id), 'members': []}
                user = User.query.filter_by(roll_no=gr.member_roll_no).first()
                if user:
                    attendance = Attendance.query.filter_by(
                        event_id=event.id, student_id=user.id).first()
                    # Get leader's registration for payment info
                    leader_reg = Registration.query.filter_by(
                        event_id=event.id,
                        student_id=gr.group_leader_id).first()
                    groups_dict[gr.group_leader_id]['members'].append({
                        'student': user,
                        'attended': attendance.attended if attendance else False,
                    })
                    groups_dict[gr.group_leader_id]['leader_reg'] = leader_reg
            registered_students = list(groups_dict.values())
        else:
            registrations = Registration.query.filter_by(event_id=event.id).all()
            for reg in registrations:
                student = User.query.get(reg.student_id)
                attendance = Attendance.query.filter_by(
                    event_id=event.id, student_id=student.id).first()
                registered_students.append({
                    'student': student,
                    'attended': attendance.attended if attendance else False,
                    'registration': reg,
                })

    # Pending payment count for badge
    pending_payments_count = event.get_pending_payments_count() if is_event_organizer else 0
    organizers = EventOrganizer.query.filter_by(event_id=event.id).all()

    return render_template('events/details.html',
                           event=event, is_registered=is_registered,
                           registered_count=registered_count,
                           registered_students=registered_students,
                           group_members=group_members,
                           is_event_organizer=is_event_organizer,
                           organizers=organizers,
                           my_registration=my_registration,
                           pending_payments_count=pending_payments_count)


@app.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    event = Event.query.get_or_404(event_id)
    if not event.is_organizer(current_user) and not current_user.is_admin():
        flash('You do not have permission to edit this event.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))

    form = EventForm(obj=event)

    if request.method == 'GET':
        if event.eligible_branch != 'all':
            form.eligible_branch.data = event.get_eligible_branches()
        if event.eligible_year != 'all':
            form.eligible_year.data = event.get_eligible_years()
        form.eligible_college.data = event.eligible_college
        form.requires_payment.data = event.requires_payment
        form.payment_amount.data = event.payment_amount
        form.payment_note.data = event.payment_note
        fc = event.get_faculty_coordinator()
        if fc:
            form.faculty_coordinator_username.data = fc.username
        co_organizers = EventOrganizer.query.filter_by(
            event_id=event.id, role='co_organizer').all()
        form.co_organizer_usernames.data = ','.join(
            [User.query.get(o.user_id).username for o in co_organizers])

    if form.validate_on_submit():
        # Validate payment QR: required if payment is enabled and no existing QR
        if form.requires_payment.data and not event.payment_qr_path:
            if not form.payment_qr.data or not form.payment_qr.data.filename:
                flash('Please upload a QR code image for payment.', 'danger')
                return render_template('events/edit.html', form=form, event=event)

        changes = get_event_changes(event, form)

        event.title = form.title.data
        event.description = form.description.data
        event.event_type = form.event_type.data
        event.venue = form.venue.data
        event.start_date = form.start_date.data
        event.end_date = form.end_date.data
        event.start_time = form.start_time.data
        event.end_time = form.end_time.data
        event.max_participants = form.max_participants.data
        event.eligible_college = form.eligible_college.data
        event.eligible_branch = ','.join(form.eligible_branch.data) if form.eligible_branch.data else 'all'
        event.eligible_year = ','.join(form.eligible_year.data) if form.eligible_year.data else 'all'
        event.requires_payment = form.requires_payment.data
        event.payment_note = form.payment_note.data if form.requires_payment.data else None

        if form.requires_payment.data:
            event.payment_amount = form.payment_amount.data
            # Replace QR if new one uploaded
            if form.payment_qr.data and form.payment_qr.data.filename:
                qr_filename = save_upload(form.payment_qr.data, QR_UPLOAD_FOLDER,
                                          ALLOWED_QR_EXT, prefix='qr')
                if qr_filename:
                    event.payment_qr_path = qr_filename
                else:
                    flash('Invalid QR file. Use JPG or PNG under 5MB.', 'danger')
                    return render_template('events/edit.html', form=form, event=event)
        else:
            event.payment_amount = None
            event.payment_qr_path = None

        EventOrganizer.query.filter(
            EventOrganizer.event_id == event.id,
            EventOrganizer.role != 'creator'
        ).delete()
        db.session.flush()

        errors = process_organizers(event, form)
        if errors:
            db.session.rollback()
            for err in errors:
                flash(err, 'danger')
            return render_template('events/edit.html', form=form, event=event)

        try:
            db.session.commit()
            if changes:
                server_name = app.config.get('SERVER_NAME', '127.0.0.1:5000')
                event_url = f"http://{server_name}/events/{event.id}"
                registrations = Registration.query.filter_by(event_id=event.id).all()
                for reg in registrations:
                    student = User.query.get(reg.student_id)
                    msg = f'Event "{event.title}" was updated. Changes: ' + '; '.join(changes)
                    create_notification(student.id, event.id, '📢 Event Updated', msg, 'push')
                    if student.email_notifications:
                        send_event_update_email(student.email, student.full_name,
                                                event.title, changes, event_url)
                db.session.commit()
                flash(f'Event updated. {len(registrations)} registered students notified.', 'success')
            else:
                flash('Event updated.', 'info')
            return redirect(url_for('event_details', event_id=event.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Failed: {str(e)}', 'danger')

    return render_template('events/edit.html', form=form, event=event)


# ─────────────────────────── REGISTRATION ───────────────────────────

@app.route('/events/<int:event_id>/register', methods=['GET', 'POST'])
@login_required
def register_event(event_id):
    if not (current_user.is_student() or current_user.is_student_coordinator()):
        flash('Only students can register for events.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))

    event = Event.query.get_or_404(event_id)

    if not event.is_user_eligible(current_user):
        flash('You are not eligible to register for this event.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))

    if event.start_date < date.today():
        flash('Cannot register for past events.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))

    if event.is_full():
        flash('This event is full.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))

    # ── INDIVIDUAL ──
    if event.participation_type == 'individual':
        existing = Registration.query.filter_by(
            event_id=event.id, student_id=current_user.id).first()
        if existing:
            flash('You are already registered.', 'warning')
            return redirect(url_for('event_details', event_id=event_id))

        form = ReceiptUploadForm()
        # If payment required, validate receipt on POST
        if request.method == 'POST':
            if event.requires_payment:
                if not form.validate_on_submit():
                    return render_template('events/payment_register.html',
                                           event=event, form=form)
                receipt_filename = save_upload(
                    form.receipt.data, RECEIPT_UPLOAD_FOLDER,
                    ALLOWED_RECEIPT_EXT, prefix=f'rcpt_u{current_user.id}_e{event.id}')
                if not receipt_filename:
                    flash('Invalid receipt file. Use JPG, PNG or PDF under 5MB.', 'danger')
                    return render_template('events/payment_register.html',
                                           event=event, form=form)
                registration = Registration(
                    event_id=event.id, student_id=current_user.id,
                    receipt_path=receipt_filename, payment_status='pending',
                    status='pending', receipt_uploaded_at=datetime.utcnow()
                )
            else:
                registration = Registration(
                    event_id=event.id, student_id=current_user.id,
                    payment_status='not_required', status='confirmed'
                )

            try:
                db.session.add(registration)
                db.session.commit()
                if event.requires_payment:
                    create_notification(current_user.id, event.id,
                                        '⏳ Registration Pending Payment Verification',
                                        f'Your receipt for "{event.title}" has been submitted. '
                                        f'Awaiting organizer verification.', 'push')
                    # Notify organizers
                    server_name = app.config.get('SERVER_NAME', '127.0.0.1:5000')
                    event_url = f"http://{server_name}/events/{event.id}"
                    for org in event.organizers:
                        org_user = User.query.get(org.user_id)
                        create_notification(org.user_id, event.id,
                                            '💳 Payment Receipt Submitted',
                                            f'{current_user.full_name} submitted a payment receipt for "{event.title}".',
                                            'push')
                        if org_user and org_user.email_notifications:
                            send_payment_receipt_email(org_user.email, org_user.full_name,
                                                       current_user.full_name, event.title, event_url)
                    db.session.commit()
                    flash('Receipt submitted! Your registration is pending payment verification.', 'info')
                else:
                    create_notification(current_user.id, event.id, '✅ Registration Confirmed!',
                                        f'You registered for "{event.title}" on '
                                        f'{event.start_date.strftime("%B %d, %Y")}.', 'push')
                    for org in event.organizers:
                        create_notification(org.user_id, event.id, '📋 New Registration',
                                            f'{current_user.full_name} registered for "{event.title}".', 'push')
                    db.session.commit()
                    flash(f'Successfully registered for "{event.title}"!', 'success')
                return redirect(url_for('event_details', event_id=event_id))
            except Exception as e:
                db.session.rollback()
                flash(f'Failed to register: {str(e)}', 'danger')
                return redirect(url_for('event_details', event_id=event_id))

        # GET — show payment page or just redirect to confirm
        if event.requires_payment:
            return render_template('events/payment_register.html', event=event, form=form)
        else:
            # No payment, auto-POST logic — redirect back with a flash asking confirmation
            return render_template('events/payment_register.html', event=event, form=form)

    # ── GROUP ──
    else:
        if not current_user.roll_no:
            flash('Please update your profile with your roll number.', 'danger')
            return redirect(url_for('profile'))

        existing_group = GroupRegistration.query.filter_by(
            event_id=event.id, group_leader_id=current_user.id).first()
        if existing_group:
            flash('You have already registered a group for this event.', 'warning')
            return redirect(url_for('event_details', event_id=event_id))

        existing_member = GroupRegistration.query.filter_by(
            event_id=event.id, member_roll_no=current_user.roll_no).first()
        if existing_member:
            flash('You are already registered as a member of another group.', 'warning')
            return redirect(url_for('event_details', event_id=event_id))

        form = GroupRegistrationForm()
        group_members_needed = event.group_size - 1
        while len(form.members) < group_members_needed:
            form.members.append_entry()

        if form.validate_on_submit():
            # Validate receipt if payment required
            if event.requires_payment:
                if not form.receipt.data or not form.receipt.data.filename:
                    flash('Please upload the payment receipt for your group.', 'danger')
                    return render_template('events/group_register.html',
                                           form=form, event=event, group_size=event.group_size)
                receipt_filename = save_upload(
                    form.receipt.data, RECEIPT_UPLOAD_FOLDER,
                    ALLOWED_RECEIPT_EXT,
                    prefix=f'rcpt_g{current_user.id}_e{event.id}')
                if not receipt_filename:
                    flash('Invalid receipt file. Use JPG, PNG or PDF under 5MB.', 'danger')
                    return render_template('events/group_register.html',
                                           form=form, event=event, group_size=event.group_size)
            else:
                receipt_filename = None

            all_members = [current_user]
            member_roll_nos = [current_user.roll_no]

            for member_data in form.members.data:
                roll_no = member_data['roll_no']
                full_name = member_data['full_name']
                existing_member = GroupRegistration.query.filter_by(
                    event_id=event.id, member_roll_no=roll_no).first()
                if existing_member:
                    flash(f'Roll number {roll_no} is already registered.', 'danger')
                    return render_template('events/group_register.html',
                                           form=form, event=event, group_size=event.group_size)
                user = User.query.filter_by(roll_no=roll_no).first()
                if not user:
                    flash(f'Student {roll_no} is not registered on CampusLink.', 'danger')
                    return render_template('events/group_register.html',
                                           form=form, event=event, group_size=event.group_size)
                if not user.email_verified:
                    flash(f'Student {full_name} has not verified their email.', 'danger')
                    return render_template('events/group_register.html',
                                           form=form, event=event, group_size=event.group_size)
                if roll_no in member_roll_nos:
                    flash(f'Duplicate roll number: {roll_no}.', 'danger')
                    return render_template('events/group_register.html',
                                           form=form, event=event, group_size=event.group_size)
                member_roll_nos.append(roll_no)
                all_members.append(user)

            for member in all_members:
                existing_reg = Registration.query.filter_by(
                    event_id=event.id, student_id=member.id).first()
                if existing_reg:
                    flash(f'{member.full_name} is already individually registered.', 'danger')
                    return render_template('events/group_register.html',
                                           form=form, event=event, group_size=event.group_size)

            try:
                leader_reg = GroupRegistration(
                    event_id=event.id, group_leader_id=current_user.id,
                    member_roll_no=current_user.roll_no, member_name=current_user.full_name)
                db.session.add(leader_reg)
                db.session.flush()

                group_registrations = [leader_reg]
                for member_data in form.members.data:
                    member_reg = GroupRegistration(
                        event_id=event.id, group_leader_id=current_user.id,
                        member_roll_no=member_data['roll_no'],
                        member_name=member_data['full_name'])
                    db.session.add(member_reg)
                    db.session.flush()
                    group_registrations.append(member_reg)

                # Create Registration records; only leader gets receipt
                for i, group_reg in enumerate(group_registrations):
                    user = User.query.filter_by(roll_no=group_reg.member_roll_no).first()
                    if user:
                        is_leader = (user.id == current_user.id)
                        reg = Registration(
                            event_id=event.id, student_id=user.id,
                            group_registration_id=group_reg.id,
                            receipt_path=receipt_filename if is_leader else None,
                            payment_status=('pending' if event.requires_payment else 'not_required'),
                            status=('pending' if event.requires_payment else 'confirmed'),
                            receipt_uploaded_at=datetime.utcnow() if (is_leader and receipt_filename) else None
                        )
                        db.session.add(reg)

                db.session.commit()

                notif_msg = (f'Your group is registered for "{event.title}". '
                             + ('Receipt submitted, awaiting payment verification.'
                                if event.requires_payment else 'Registration confirmed!'))
                for member in all_members:
                    create_notification(member.id, event.id,
                                        '⏳ Group Registration Pending' if event.requires_payment
                                        else '✅ Group Registration Confirmed!',
                                        notif_msg, 'push')

                if event.requires_payment:
                    server_name = app.config.get('SERVER_NAME', '127.0.0.1:5000')
                    event_url = f"http://{server_name}/events/{event.id}"
                    for org in event.organizers:
                        org_user = User.query.get(org.user_id)
                        create_notification(org.user_id, event.id,
                                            '💳 Group Payment Receipt Submitted',
                                            f'Group led by {current_user.full_name} submitted receipt for "{event.title}".',
                                            'push')
                        if org_user and org_user.email_notifications:
                            send_payment_receipt_email(org_user.email, org_user.full_name,
                                                       current_user.full_name, event.title, event_url)
                else:
                    for org in event.organizers:
                        create_notification(org.user_id, event.id, '📋 New Group Registration',
                                            f'Group of {event.group_size} led by {current_user.full_name} registered.',
                                            'push')
                db.session.commit()
                if event.requires_payment:
                    flash('Group receipt submitted! Awaiting payment verification.', 'info')
                else:
                    flash(f'Group registered for "{event.title}"!', 'success')
                return redirect(url_for('event_details', event_id=event_id))
            except Exception as e:
                db.session.rollback()
                flash(f'Failed to register group: {str(e)}', 'danger')

        return render_template('events/group_register.html',
                               form=form, event=event, group_size=event.group_size)


# ─────────────────────────── PAYMENT VERIFICATION ───────────────────────────

@app.route('/events/<int:event_id>/payment/<int:reg_id>/verify', methods=['POST'])
@login_required
def verify_payment(event_id, reg_id):
    event = Event.query.get_or_404(event_id)
    if not event.is_organizer(current_user) and not current_user.is_admin():
        flash('Permission denied.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))

    registration = Registration.query.get_or_404(reg_id)
    decision = request.form.get('decision')  # 'approve' or 'reject'
    rejection_note = request.form.get('rejection_note', '').strip()

    student = User.query.get(registration.student_id)
    server_name = app.config.get('SERVER_NAME', '127.0.0.1:5000')
    event_url = f"http://{server_name}/events/{event_id}"

    if decision == 'approve':
        registration.payment_status = 'approved'
        registration.payment_rejection_note = None

        # For group events — approve all members in the same group
        if registration.group_registration_id:
            group_reg = GroupRegistration.query.get(registration.group_registration_id)
            if group_reg:
                all_group_regs = Registration.query.filter_by(
                    event_id=event_id,
                ).join(GroupRegistration,
                       Registration.group_registration_id == GroupRegistration.id
                ).filter(GroupRegistration.group_leader_id == group_reg.group_leader_id).all()
                for r in all_group_regs:
                    r.payment_status = 'approved'
                    r.status = 'confirmed'
                    member = User.query.get(r.student_id)
                    if member:
                        create_notification(member.id, event_id, '✅ Payment Approved!',
                                            f'Your payment for "{event.title}" is approved. '
                                            f'Registration confirmed!', 'push')
                        if member.email_notifications:
                            send_payment_approved_email(member.email, member.full_name,
                                                        event.title, event_url)
        else:
            registration.status = 'confirmed'
            create_notification(student.id, event_id, '✅ Payment Approved!',
                                f'Your payment for "{event.title}" is approved. Registration confirmed!', 'push')
            if student and student.email_notifications:
                send_payment_approved_email(student.email, student.full_name, event.title, event_url)

        flash(f'Payment approved for {student.full_name}.', 'success')

    elif decision == 'reject':
        registration.payment_status = 'rejected'
        registration.payment_rejection_note = rejection_note or 'Payment could not be verified.'

        # For group — reject all members
        if registration.group_registration_id:
            group_reg = GroupRegistration.query.get(registration.group_registration_id)
            if group_reg:
                all_group_regs = Registration.query.filter_by(
                    event_id=event_id,
                ).join(GroupRegistration,
                       Registration.group_registration_id == GroupRegistration.id
                ).filter(GroupRegistration.group_leader_id == group_reg.group_leader_id).all()
                for r in all_group_regs:
                    r.payment_status = 'rejected'
                    r.payment_rejection_note = rejection_note or 'Payment could not be verified.'
                    member = User.query.get(r.student_id)
                    if member:
                        create_notification(member.id, event_id, '❌ Payment Rejected',
                                            f'Your payment for "{event.title}" was rejected. '
                                            f'Reason: {rejection_note or "N/A"}. Please re-upload.', 'push')
                        if member.email_notifications:
                            send_payment_rejected_email(member.email, member.full_name,
                                                        event.title, rejection_note, event_url)
        else:
            create_notification(student.id, event_id, '❌ Payment Rejected',
                                f'Your payment for "{event.title}" was rejected. '
                                f'Reason: {rejection_note or "N/A"}. Please re-upload.', 'push')
            if student and student.email_notifications:
                send_payment_rejected_email(student.email, student.full_name,
                                            event.title, rejection_note, event_url)

        flash(f'Payment rejected for {student.full_name}.', 'info')

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Failed: {str(e)}', 'danger')

    return redirect(url_for('event_details', event_id=event_id))


@app.route('/events/<int:event_id>/reupload_receipt', methods=['GET', 'POST'])
@login_required
def reupload_receipt(event_id):
    """Allow student to re-upload receipt after rejection."""
    registration = Registration.query.filter_by(
        event_id=event_id, student_id=current_user.id).first_or_404()

    if registration.payment_status not in ('rejected', 'pending'):
        flash('No re-upload needed.', 'info')
        return redirect(url_for('event_details', event_id=event_id))

    event = Event.query.get_or_404(event_id)
    form = ReceiptUploadForm()

    if form.validate_on_submit():
        receipt_filename = save_upload(
            form.receipt.data, RECEIPT_UPLOAD_FOLDER,
            ALLOWED_RECEIPT_EXT,
            prefix=f'rcpt_u{current_user.id}_e{event_id}')
        if not receipt_filename:
            flash('Invalid file. Use JPG, PNG or PDF under 5MB.', 'danger')
            return render_template('events/reupload_receipt.html', form=form, event=event,
                                   registration=registration)

        registration.receipt_path = receipt_filename
        registration.payment_status = 'pending'
        registration.payment_rejection_note = None
        registration.receipt_uploaded_at = datetime.utcnow()

        # For group — reset all members to pending
        if registration.group_registration_id:
            group_reg = GroupRegistration.query.get(registration.group_registration_id)
            if group_reg and group_reg.group_leader_id == current_user.id:
                all_group_regs = Registration.query.filter_by(
                    event_id=event_id,
                ).join(GroupRegistration,
                       Registration.group_registration_id == GroupRegistration.id
                ).filter(GroupRegistration.group_leader_id == current_user.id).all()
                for r in all_group_regs:
                    r.payment_status = 'pending'
                    r.payment_rejection_note = None
            elif group_reg and group_reg.group_leader_id != current_user.id:
                flash('Only the group leader can re-upload the receipt.', 'danger')
                return redirect(url_for('event_details', event_id=event_id))

        try:
            db.session.commit()
            # Notify organizers
            server_name = app.config.get('SERVER_NAME', '127.0.0.1:5000')
            event_url = f"http://{server_name}/events/{event_id}"
            for org in event.organizers:
                org_user = User.query.get(org.user_id)
                create_notification(org.user_id, event_id,
                                    '💳 Receipt Re-uploaded',
                                    f'{current_user.full_name} re-uploaded payment receipt for "{event.title}". Please re-verify.',
                                    'push')
                if org_user and org_user.email_notifications:
                    send_payment_receipt_email(org_user.email, org_user.full_name,
                                               current_user.full_name, event.title, event_url)
            db.session.commit()
            flash('Receipt re-uploaded! Awaiting verification.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Failed: {str(e)}', 'danger')
        return redirect(url_for('event_details', event_id=event_id))

    return render_template('events/reupload_receipt.html', form=form, event=event,
                           registration=registration)


@app.route('/events/<int:event_id>/cancel')
@login_required
def cancel_registration(event_id):
    if not (current_user.is_student() or current_user.is_student_coordinator()):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    registration = Registration.query.filter_by(
        event_id=event_id, student_id=current_user.id).first_or_404()
    event = Event.query.get(event_id)

    if event.start_date < date.today():
        flash('Cannot cancel past events.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))

    if event.participation_type == 'group' and registration.group_registration_id:
        group_reg = GroupRegistration.query.get(registration.group_registration_id)
        if group_reg and group_reg.group_leader_id == current_user.id:
            group_registrations = GroupRegistration.query.filter_by(
                event_id=event.id, group_leader_id=current_user.id).all()
            for gr in group_registrations:
                Registration.query.filter_by(
                    event_id=event.id, group_registration_id=gr.id).delete()
                db.session.delete(gr)
        else:
            flash('Only the group leader can cancel the group registration.', 'danger')
            return redirect(url_for('event_details', event_id=event_id))
    else:
        db.session.delete(registration)

    for org in event.organizers:
        create_notification(org.user_id, event.id, '❌ Registration Cancelled',
                            f'{current_user.full_name} cancelled registration for "{event.title}".', 'push')
    try:
        db.session.commit()
        flash(f'Registration cancelled.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed: {str(e)}', 'danger')

    return redirect(url_for('events'))


# ─────────────────────────── ATTENDANCE ───────────────────────────

@app.route('/attendance/<int:event_id>/mark', methods=['GET', 'POST'])
@login_required
def mark_attendance(event_id):
    event = Event.query.get_or_404(event_id)
    if not event.is_organizer(current_user) and not current_user.is_admin():
        flash('Permission denied.', 'danger')
        return redirect(url_for('dashboard'))
    if event.start_date > date.today():
        flash('Cannot mark attendance for future events.', 'danger')
        return redirect(url_for('event_details', event_id=event_id))

    if event.participation_type == 'group':
        groups = GroupRegistration.query.filter_by(event_id=event.id).all()
        group_dict = {}
        for gr in groups:
            if gr.group_leader_id not in group_dict:
                group_dict[gr.group_leader_id] = []
            user = User.query.filter_by(roll_no=gr.member_roll_no).first()
            if user:
                group_dict[gr.group_leader_id].append(user)
        registrations = [{'group_leader': User.query.get(lid), 'members': members, 'group_id': lid}
                         for lid, members in group_dict.items()]
    else:
        # Only confirmed registrations for attendance
        registrations = Registration.query.filter_by(
            event_id=event.id, status='confirmed').all()

    if not registrations:
        flash('No confirmed students registered.', 'warning')
        return redirect(url_for('event_details', event_id=event_id))

    if request.method == 'POST':
        if event.participation_type == 'group':
            for reg_group in registrations:
                group_id = reg_group['group_id']
                attended = request.form.get(f'attendance_group_{group_id}') == 'on'
                for member in reg_group['members']:
                    att = Attendance.query.filter_by(event_id=event.id, student_id=member.id).first()
                    if att:
                        att.attended = attended
                        att.marked_by = current_user.id
                        att.marked_at = datetime.now()
                    else:
                        db.session.add(Attendance(event_id=event.id, student_id=member.id,
                                                  attended=attended, marked_by=current_user.id))
                    status_word = 'PRESENT' if attended else 'ABSENT'
                    create_notification(member.id, event.id,
                                        '✅ Attendance Marked' if attended else '📝 Attendance Marked',
                                        f'Attendance for "{event.title}" marked as {status_word}.', 'email')
        else:
            for reg in registrations:
                attended = request.form.get(f'attendance_{reg.student_id}') == 'on'
                att = Attendance.query.filter_by(event_id=event.id, student_id=reg.student_id).first()
                if att:
                    att.attended = attended
                    att.marked_by = current_user.id
                    att.marked_at = datetime.now()
                else:
                    db.session.add(Attendance(event_id=event.id, student_id=reg.student_id,
                                              attended=attended, marked_by=current_user.id))
                status_word = 'PRESENT' if attended else 'ABSENT'
                create_notification(reg.student_id, event.id,
                                    '✅ Attendance Marked' if attended else '📝 Attendance Marked',
                                    f'Attendance for "{event.title}" marked as {status_word}.', 'email')
        try:
            db.session.commit()
            flash('Attendance saved!', 'success')
            return redirect(url_for('event_details', event_id=event.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Failed: {str(e)}', 'danger')

    attendance_records = {}
    if event.participation_type == 'group':
        for reg_group in registrations:
            for member in reg_group['members']:
                att = Attendance.query.filter_by(event_id=event.id, student_id=member.id).first()
                attendance_records[member.id] = att.attended if att else False
    else:
        for reg in registrations:
            att = Attendance.query.filter_by(event_id=event.id, student_id=reg.student_id).first()
            attendance_records[reg.student_id] = att.attended if att else False

    return render_template('attendance/mark.html', event=event, registrations=registrations,
                           attendance_records=attendance_records,
                           is_group=(event.participation_type == 'group'))


# ─────────────────────────── NOTIFICATIONS ───────────────────────────

@app.route('/notifications')
@login_required
def notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc()).all()
    for notif in notifs:
        notif.is_read = True
    try:
        db.session.commit()
    except:
        db.session.rollback()
    return render_template('notifications.html', notifications=notifs)


# ─────────────────────────── PROFILE ───────────────────────────

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

    if current_user.is_student() or current_user.is_student_coordinator():
        my_events_count = Registration.query.filter_by(student_id=current_user.id).count()
        registrations = Registration.query.filter_by(student_id=current_user.id).all()
        total_registrations = len(registrations)
        attended_count = sum(
            1 for reg in registrations
            if Attendance.query.filter_by(event_id=reg.event_id,
                                          student_id=current_user.id, attended=True).first()
        )
        attendance_percentage = (attended_count / total_registrations * 100) if total_registrations > 0 else 0
    else:
        my_events_count = Event.query.filter_by(created_by=current_user.id).count()
        attendance_percentage = 0

    latest_app = CoordinatorApplication.query.filter_by(user_id=current_user.id)\
        .order_by(CoordinatorApplication.applied_at.desc()).first()

    return render_template('profile.html', my_events_count=my_events_count,
                           attendance_percentage=int(attendance_percentage),
                           form=form, latest_coordinator_app=latest_app)


# ─────────────────────────── ADMIN ───────────────────────────

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_events = Event.query.count()
    total_registrations = Registration.query.count()
    total_attendance = Attendance.query.filter_by(attended=True).count()
    pending_apps = CoordinatorApplication.query.filter_by(status='pending').count()
    pending_payments = Registration.query.filter_by(payment_status='pending').count()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_events = Event.query.order_by(Event.created_at.desc()).limit(5).all()
    return render_template('admin/dashboard.html',
                           total_users=total_users, total_events=total_events,
                           total_registrations=total_registrations,
                           total_attendance=total_attendance,
                           pending_apps=pending_apps,
                           pending_payments=pending_payments,
                           recent_users=recent_users, recent_events=recent_events)


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
    if new_role in ['admin', 'faculty', 'student_coordinator', 'student']:
        old_role = user.role
        user.role = new_role
        if old_role == 'student_coordinator' and new_role == 'student':
            user.coordinator_status = 'none'
            db.session.commit()
            send_coordinator_decision_email(user.email, user.full_name, approved=False, revoked=True)
            flash(f'Student Coordinator role revoked from {user.username}.', 'success')
        else:
            db.session.commit()
            flash(f'User {user.username} role changed to {new_role}.', 'success')
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
        GroupRegistration.query.filter_by(group_leader_id=user.id).delete()
        if user.roll_no:
            GroupRegistration.query.filter_by(member_roll_no=user.roll_no).delete()
        Event.query.filter_by(created_by=user.id).delete()
        EventOrganizer.query.filter_by(user_id=user.id).delete()
        CoordinatorApplication.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.username} deleted.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/coordinator_applications')
@login_required
@admin_required
def admin_coordinator_applications():
    pending = CoordinatorApplication.query.filter_by(status='pending')\
        .order_by(CoordinatorApplication.applied_at.desc()).all()
    reviewed = CoordinatorApplication.query.filter(CoordinatorApplication.status != 'pending')\
        .order_by(CoordinatorApplication.reviewed_at.desc()).limit(20).all()
    return render_template('admin/coordinator_applications.html',
                           pending=pending, reviewed=reviewed)


@app.route('/admin/coordinator_applications/<int:app_id>/review', methods=['POST'])
@login_required
@admin_required
def review_coordinator_application(app_id):
    application = CoordinatorApplication.query.get_or_404(app_id)
    decision = request.form.get('decision')
    applicant = User.query.get(application.user_id)
    application.reviewed_at = datetime.utcnow()
    application.reviewed_by = current_user.id
    if decision == 'approve':
        application.status = 'approved'
        applicant.role = 'student_coordinator'
        applicant.coordinator_status = 'approved'
        flash(f'{applicant.full_name} is now a Student Coordinator.', 'success')
        send_coordinator_decision_email(applicant.email, applicant.full_name, approved=True)
        create_notification(applicant.id, None, '🎉 Application Approved!',
                            'Your Student Coordinator application has been approved!', 'push')
    elif decision == 'reject':
        application.status = 'rejected'
        applicant.coordinator_status = 'rejected'
        flash(f'Application from {applicant.full_name} rejected.', 'info')
        send_coordinator_decision_email(applicant.email, applicant.full_name, approved=False)
        create_notification(applicant.id, None, '📋 Application Update',
                            'Your coordinator application was not approved at this time.', 'push')
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Failed: {str(e)}', 'danger')
    return redirect(url_for('admin_coordinator_applications'))


@app.route('/admin/stats')
@login_required
@admin_required
def admin_stats():
    users_count = User.query.count()
    faculty_count = User.query.filter_by(role='faculty').count()
    student_count = User.query.filter_by(role='student').count()
    coordinator_count = User.query.filter_by(role='student_coordinator').count()
    admin_count = User.query.filter_by(role='admin').count()
    events_count = Event.query.count()
    upcoming_events = Event.query.filter(Event.start_date >= date.today()).count()
    completed_events = Event.query.filter(Event.start_date < date.today()).count()
    registrations_count = Registration.query.count()
    attendance_count = Attendance.query.filter_by(attended=True).count()
    group_events_count = Event.query.filter_by(participation_type='group').count()
    group_registrations_count = GroupRegistration.query.count()
    mgit_users = User.query.filter_by(college='MGIT').count()
    other_users = User.query.filter(User.college != 'MGIT').count()
    paid_events = Event.query.filter_by(requires_payment=True).count()
    pending_payments = Registration.query.filter_by(payment_status='pending').count()
    approved_payments = Registration.query.filter_by(payment_status='approved').count()
    return render_template('admin/stats.html',
                           users_count=users_count, faculty_count=faculty_count,
                           student_count=student_count, coordinator_count=coordinator_count,
                           admin_count=admin_count, events_count=events_count,
                           upcoming_events=upcoming_events, completed_events=completed_events,
                           registrations_count=registrations_count,
                           attendance_count=attendance_count,
                           group_events_count=group_events_count,
                           group_registrations_count=group_registrations_count,
                           mgit_users=mgit_users, other_users=other_users,
                           paid_events=paid_events, pending_payments=pending_payments,
                           approved_payments=approved_payments)


@app.route('/send_reminders_manual')
@login_required
@admin_required
def send_reminders_manual():
    send_automatic_reminders()
    flash('Reminders sent!', 'success')
    return redirect(url_for('admin_dashboard'))


# ─────────────────────────── ERROR HANDLERS ───────────────────────────

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500


# ─────────────────────────── RUN ───────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Database tables created/verified!")
    print("\n✅ CampusLink is running!")
    print("📍 Access at: http://127.0.0.1:5000")
    print("=" * 50)
    app.run(debug=True, host='127.0.0.1', port=5000)