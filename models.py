from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    roll_no = db.Column(db.String(50), unique=True, nullable=True)  # New field
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.Enum('admin', 'faculty', 'student'), default='student')
    full_name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    email_notifications = db.Column(db.Boolean, default=True)
    push_notifications = db.Column(db.Boolean, default=True)
    
    
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(200), unique=True)
    token_created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def generate_verification_token(self):
        """Generate a unique verification token"""
        token = secrets.token_urlsafe(32)
        self.verification_token = token
        self.token_created_at = datetime.utcnow()
        return token
    
    def is_admin(self):
        return self.role == 'admin'
    
    def is_faculty(self):
        return self.role in ['faculty', 'admin']
    
    def is_student(self):
        return self.role == 'student'
    
    def is_verified(self):
        return self.email_verified

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
    
    creator = db.relationship('User', foreign_keys=[created_by])
    event_groups = db.relationship('EventGroup', backref='event', cascade='all, delete-orphan')
    
    def get_registration_count(self):
        from sqlalchemy import func
        
        if self.participation_type == 'group':
            return GroupRegistration.query.filter_by(event_id=self.id).distinct(GroupRegistration.group_leader_id).count()
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

class Registration(db.Model):
    __tablename__ = 'registrations'
    
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    registration_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.Enum('pending', 'confirmed', 'cancelled'), default='confirmed')
    group_registration_id = db.Column(db.Integer, db.ForeignKey('group_registrations.id'))
    
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