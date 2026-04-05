from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets

db = SQLAlchemy()

BRANCH_CHOICES = [
    ('CIVIL', 'Civil Engineering'),
    ('MECH', 'Mechanical Engineering'),
    ('EEE', 'Electrical & Electronics Engineering'),
    ('ECE', 'Electronics & Communication Engineering'),
    ('CSE', 'Computer Science Engineering'),
    ('IT', 'Information Technology'),
    ('ET', 'Engineering Technology'),
    ('MME', 'Metallurgical & Materials Engineering'),
    ('P&C', 'Petroleum & Chemical Engineering'),
    ('M&H', 'Mathematics & Humanities'),
]

YEAR_CHOICES = [
    ('1', '1st Year'),
    ('2', '2nd Year'),
    ('3', '3rd Year'),
    ('4', '4th Year'),
    ('M1', 'M.Tech 1st Year'),
    ('M2', 'M.Tech 2nd Year'),
]


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    roll_no = db.Column(db.String(50), unique=True, nullable=True)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.Enum('admin', 'faculty', 'student_coordinator', 'student'), default='student')
    full_name = db.Column(db.String(100), nullable=False)

    college = db.Column(db.String(20), default='other')
    college_name = db.Column(db.String(150), nullable=True)
    branch = db.Column(db.String(20), nullable=True)
    year = db.Column(db.String(5), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    email_notifications = db.Column(db.Boolean, default=True)
    push_notifications = db.Column(db.Boolean, default=True)

    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(200), unique=True)
    token_created_at = db.Column(db.DateTime, default=datetime.utcnow)

    coordinator_status = db.Column(db.Enum('none', 'pending', 'approved', 'rejected'), default='none')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_verification_token(self):
        token = secrets.token_urlsafe(32)
        self.verification_token = token
        self.token_created_at = datetime.utcnow()
        return token

    def is_admin(self):
        return self.role == 'admin'

    def is_faculty(self):
        return self.role in ['faculty', 'admin']

    def is_student_coordinator(self):
        return self.role == 'student_coordinator'

    def is_student(self):
        return self.role == 'student'

    def can_create_events(self):
        return self.role in ['admin', 'faculty', 'student_coordinator']

    def is_verified(self):
        return self.email_verified

    def get_college_display(self):
        if self.college == 'MGIT':
            return 'MGIT'
        return self.college_name or 'Other'

    def get_year_display(self):
        year_map = dict(YEAR_CHOICES)
        return year_map.get(self.year, self.year or 'N/A')


class CoordinatorApplication(db.Model):
    __tablename__ = 'coordinator_applications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.Enum('pending', 'approved', 'rejected'), default='pending')
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reason = db.Column(db.Text, nullable=True)

    user = db.relationship('User', foreign_keys=[user_id], backref='coordinator_applications')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])


class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    event_type = db.Column(db.Enum('academic', 'cultural', 'sports', 'workshop'), nullable=False)
    participation_type = db.Column(db.Enum('individual', 'group'), default='individual')
    group_size = db.Column(db.Integer, default=1)
    venue = db.Column(db.String(200))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    max_participants = db.Column(db.Integer, default=100)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Eligibility filters
    eligible_college = db.Column(db.String(20), default='all')
    eligible_branch = db.Column(db.String(200), default='all')
    eligible_year = db.Column(db.String(100), default='all')

    # Payment
    requires_payment = db.Column(db.Boolean, default=False)
    payment_amount = db.Column(db.Numeric(10, 2), nullable=True)
    payment_qr_path = db.Column(db.String(300), nullable=True)
    payment_note = db.Column(db.String(500), nullable=True)

    creator = db.relationship('User', foreign_keys=[created_by])
    event_groups = db.relationship('EventGroup', backref='event', cascade='all, delete-orphan')
    organizers = db.relationship('EventOrganizer', backref='event', cascade='all, delete-orphan')

    def get_registration_count(self):
        if self.participation_type == 'group':
            return GroupRegistration.query.filter_by(event_id=self.id)\
                .distinct(GroupRegistration.group_leader_id).count()
        return Registration.query.filter_by(event_id=self.id).count()

    def is_full(self):
        return self.get_registration_count() >= self.max_participants

    def get_status(self):
        now = datetime.now()
        event_start = datetime.combine(self.start_date, self.start_time)
        event_end = datetime.combine(self.end_date or self.start_date, self.end_time)
        if now < event_start:
            return 'upcoming'
        elif event_start <= now <= event_end:
            return 'ongoing'
        else:
            return 'completed'

    def get_eligible_branches(self):
        if self.eligible_branch == 'all':
            return 'all'
        return [b.strip() for b in self.eligible_branch.split(',')]

    def get_eligible_years(self):
        if self.eligible_year == 'all':
            return 'all'
        return [y.strip() for y in self.eligible_year.split(',')]

    def is_user_eligible(self, user):
        if self.eligible_college != 'all':
            if self.eligible_college == 'MGIT' and user.college != 'MGIT':
                return False
            if self.eligible_college == 'other' and user.college == 'MGIT':
                return False
        eligible_branches = self.get_eligible_branches()
        if eligible_branches != 'all' and user.branch not in eligible_branches:
            return False
        eligible_years = self.get_eligible_years()
        if eligible_years != 'all' and user.year not in eligible_years:
            return False
        return True

    def get_organizer_ids(self):
        return [o.user_id for o in self.organizers]

    def is_organizer(self, user):
        return user.id in self.get_organizer_ids() or self.created_by == user.id

    def get_faculty_coordinator(self):
        fc = EventOrganizer.query.filter_by(event_id=self.id, role='faculty_coordinator').first()
        if fc:
            return User.query.get(fc.user_id)
        return None

    def get_pending_payments_count(self):
        return Registration.query.filter_by(
            event_id=self.id, payment_status='pending'
        ).count()


class EventOrganizer(db.Model):
    __tablename__ = 'event_organizers'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role = db.Column(db.Enum('creator', 'co_organizer', 'faculty_coordinator'), default='co_organizer')
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User')

    __table_args__ = (
        db.UniqueConstraint('event_id', 'user_id', name='unique_organizer_per_event'),
    )


class Registration(db.Model):
    __tablename__ = 'registrations'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    registration_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.Enum('pending', 'confirmed', 'cancelled'), default='confirmed')
    group_registration_id = db.Column(db.Integer, db.ForeignKey('group_registrations.id'))

    # Payment tracking
    receipt_path = db.Column(db.String(300), nullable=True)
    payment_status = db.Column(
        db.Enum('not_required', 'pending', 'approved', 'rejected'),
        default='not_required'
    )
    payment_rejection_note = db.Column(db.String(500), nullable=True)
    receipt_uploaded_at = db.Column(db.DateTime, nullable=True)

    event = db.relationship('Event')
    student = db.relationship('User')
    group_registration = db.relationship('GroupRegistration', backref='registrations')


class EventGroup(db.Model):
    __tablename__ = 'event_groups'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    group_size = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class GroupRegistration(db.Model):
    __tablename__ = 'group_registrations'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    group_leader_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    member_roll_no = db.Column(db.String(50), nullable=False)
    member_name = db.Column(db.String(100))
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)

    event = db.relationship('Event')
    group_leader = db.relationship('User', foreign_keys=[group_leader_id])

    __table_args__ = (
        db.UniqueConstraint('event_id', 'member_roll_no', name='unique_member_per_event'),
    )


class Attendance(db.Model):
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    attended = db.Column(db.Boolean, default=False)
    marked_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    marked_at = db.Column(db.DateTime, default=datetime.utcnow)


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'))
    title = db.Column(db.String(200))
    message = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notification_type = db.Column(db.Enum('email', 'push'), default='push')

    user = db.relationship('User')
    event = db.relationship('Event')