from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileSize
from wtforms import (StringField, TextAreaField, SelectField, IntegerField,
                     DateField, TimeField, PasswordField, SubmitField,
                     BooleanField, FieldList, FormField, RadioField,
                     SelectMultipleField, DecimalField)
from wtforms.validators import (DataRequired, Email, Length, EqualTo,
                                ValidationError, Regexp, NumberRange, Optional)
from models import BRANCH_CHOICES, YEAR_CHOICES
import re
import socket


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class NotificationSettingsForm(FlaskForm):
    email_notifications = BooleanField('Receive Email Notifications')
    push_notifications = BooleanField('Receive In-App Notifications')
    submit = SubmitField('Save Settings')


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(), Length(min=4, max=100),
        Regexp(r'^[a-zA-Z0-9_]+$', message='Username can only contain letters, numbers, and underscores.')
    ])
    email = StringField('Email', validators=[
        DataRequired(), Email(message='Please enter a valid email address.')
    ])
    roll_no = StringField('Roll Number', validators=[
        DataRequired(), Length(min=3, max=50),
        Regexp(r'^[a-zA-Z0-9_-]+$', message='Roll number can only contain letters, numbers, hyphens, and underscores.')
    ])
    password = PasswordField('Password', validators=[
        DataRequired(), Length(min=6),
        Regexp(r'^(?=.*[A-Za-z])(?=.*\d)', message='Password must contain at least one letter and one number.')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(), EqualTo('password', message='Passwords must match.')
    ])
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])

    college = RadioField('College',
        choices=[('MGIT', 'MGIT (Mahatma Gandhi Institute of Technology)'), ('other', 'Other College')],
        default='MGIT', validators=[DataRequired()])

    college_name = StringField('College Name', validators=[Optional(), Length(max=150)])

    branch = SelectField('Branch',
        choices=[('', '-- Select Branch --')] + BRANCH_CHOICES,
        validators=[Optional()])

    branch_other = StringField('Branch (Other College)', validators=[
        Optional(),
        Regexp(r'^[A-Z&/]+$', message='Branch must be uppercase abbreviation, e.g. CSE, ECE, MECH')
    ])

    year = SelectField('Year',
        choices=[('', '-- Select Year --')] + YEAR_CHOICES,
        validators=[DataRequired(message='Please select your year.')])

    role = SelectField('Role',
        choices=[('student', 'Student'), ('faculty', 'Faculty')],
        default='student', validators=[DataRequired()])

    email_notifications = BooleanField('Receive Email Notifications', default=True)
    submit = SubmitField('Register')

    def validate_username(self, username):
        from models import User
        if User.query.filter_by(username=username.data).first():
            raise ValidationError('Username already taken.')

    def validate_email(self, email):
        from models import User
        if User.query.filter_by(email=email.data).first():
            raise ValidationError('Email already registered.')
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email.data):
            raise ValidationError('Please enter a valid email address.')
        if self.college.data == 'MGIT':
            if not email.data.lower().endswith('@mgit.ac.in'):
                raise ValidationError('MGIT students must use their official @mgit.ac.in email address.')
        else:
            fake_patterns = ['test', 'example', 'fake', 'dummy', 'temp', 'mailinator', 'guerrillamail']
            for pattern in fake_patterns:
                if pattern in email.data.lower():
                    raise ValidationError('Please use a real email address.')
            try:
                domain = email.data.split('@')[1]
                socket.gethostbyname(domain)
            except:
                raise ValidationError('Email domain does not exist.')

    def validate_roll_no(self, roll_no):
        from models import User
        if User.query.filter_by(roll_no=roll_no.data).first():
            raise ValidationError('Roll number already registered.')

    def validate_college_name(self, college_name):
        if self.college.data == 'other' and not college_name.data:
            raise ValidationError('Please enter your college name.')

    def validate_branch(self, branch):
        if self.college.data == 'MGIT' and not branch.data:
            raise ValidationError('Please select your branch.')

    def validate_branch_other(self, branch_other):
        if self.college.data == 'other' and not branch_other.data:
            raise ValidationError('Please enter your branch abbreviation (e.g. CSE, MECH).')


class CoordinatorApplicationForm(FlaskForm):
    reason = TextAreaField('Why do you want to become a Student Coordinator?', validators=[
        DataRequired(), Length(min=20, max=1000)
    ])
    submit = SubmitField('Submit Application')


class MemberForm(FlaskForm):
    roll_no = StringField('Member Roll Number', validators=[DataRequired(), Length(min=3, max=50)])
    full_name = StringField('Member Full Name', validators=[DataRequired(), Length(min=2, max=100)])


BRANCH_MULTI_CHOICES = [(b[0], b[0]) for b in BRANCH_CHOICES]
YEAR_MULTI_CHOICES = [(y[0], y[1]) for y in YEAR_CHOICES]
COLLEGE_CHOICES = [('all', 'All Colleges'), ('MGIT', 'MGIT Only'), ('other', 'Other Colleges Only')]

ALLOWED_QR_EXTENSIONS = ['jpg', 'jpeg', 'png']
ALLOWED_RECEIPT_EXTENSIONS = ['jpg', 'jpeg', 'png', 'pdf']
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


class EventForm(FlaskForm):
    title = StringField('Event Title', validators=[DataRequired(), Length(min=3, max=200)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=2000)])

    event_type = SelectField('Event Type', choices=[
        ('academic', 'Academic'), ('cultural', 'Cultural'),
        ('sports', 'Sports'), ('workshop', 'Workshop')
    ], validators=[DataRequired()])

    participation_type = SelectField('Participation Type', choices=[
        ('individual', 'Individual'), ('group', 'Group')
    ], default='individual', validators=[DataRequired()])

    group_size = SelectField('Group Size',
        choices=[(2, '2 Members'), (3, '3 Members'), (4, '4 Members')],
        default=2, validators=[Optional()])

    venue = StringField('Venue', validators=[DataRequired(), Length(max=200)])
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[DataRequired()])
    end_date = DateField('End Date', format='%Y-%m-%d', validators=[Optional()])
    start_time = TimeField('Start Time', format='%H:%M', validators=[DataRequired()])
    end_time = TimeField('End Time', format='%H:%M', validators=[DataRequired()])
    max_participants = IntegerField('Maximum Participants', default=100,
                                   validators=[DataRequired(), NumberRange(min=1, max=10000)])

    # Eligibility
    eligible_college = SelectField('Eligible College', choices=COLLEGE_CHOICES, default='all')
    eligible_branch = SelectMultipleField('Eligible Branches',
                                          choices=BRANCH_MULTI_CHOICES, validators=[Optional()])
    eligible_year = SelectMultipleField('Eligible Years',
                                        choices=YEAR_MULTI_CHOICES, validators=[Optional()])

    # Organizers
    co_organizer_usernames = StringField('Co-Organizer Usernames (comma separated)', validators=[Optional()])
    faculty_coordinator_username = StringField('Faculty Coordinator Username', validators=[Optional()])

    # Payment
    requires_payment = BooleanField('This event requires payment', default=False)
    payment_amount = DecimalField('Payment Amount (₹)', places=2,
                                  validators=[Optional(), NumberRange(min=1, max=100000)])
    payment_qr = FileField('Upload Payment QR Code',
                           validators=[Optional(),
                                       FileAllowed(ALLOWED_QR_EXTENSIONS, 'Images only (JPG, PNG)!')])
    payment_note = StringField('Payment Note / UPI ID', validators=[Optional(), Length(max=500)])

    submit = SubmitField('Save Event')

    def validate_start_date(self, start_date):
        from datetime import date
        if start_date.data < date.today():
            raise ValidationError('Start date cannot be in the past.')

    def validate_end_date(self, end_date):
        if end_date.data and self.start_date.data:
            if end_date.data < self.start_date.data:
                raise ValidationError('End date cannot be before start date.')

    def validate_end_time(self, end_time):
        if self.start_date.data == (self.end_date.data or self.start_date.data):
            if self.start_time.data and end_time.data:
                if end_time.data <= self.start_time.data:
                    raise ValidationError('End time must be after start time.')

    def validate_payment_amount(self, payment_amount):
        if self.requires_payment.data and not payment_amount.data:
            raise ValidationError('Please enter the payment amount.')

    def validate_payment_qr(self, payment_qr):
        # QR is required only when creating a new paid event (no existing QR)
        # This is handled in the route since we need to know if existing QR exists
        pass


class ReceiptUploadForm(FlaskForm):
    receipt = FileField('Upload Payment Receipt', validators=[
        DataRequired(message='Please upload your payment receipt.'),
        FileAllowed(ALLOWED_RECEIPT_EXTENSIONS, 'Only JPG, PNG, or PDF files allowed!')
    ])
    submit = SubmitField('Submit Receipt')


class GroupRegistrationForm(FlaskForm):
    members = FieldList(FormField(MemberForm), min_entries=1)
    receipt = FileField('Upload Payment Receipt (Group)', validators=[
        FileAllowed(ALLOWED_RECEIPT_EXTENSIONS, 'Only JPG, PNG, or PDF files allowed!')
    ])
    submit = SubmitField('Register Group')