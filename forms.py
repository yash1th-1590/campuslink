from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, IntegerField, DateField, TimeField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, Regexp, NumberRange
from models import User
import re
import socket

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(message='Username is required.')
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message='Password is required.')
    ])
    submit = SubmitField('Login')

class NotificationSettingsForm(FlaskForm):
    email_notifications = BooleanField('Receive Email Notifications')
    push_notifications = BooleanField('Receive In-App Notifications')
    submit = SubmitField('Save Settings')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(message='Username is required.'),
        Length(min=4, max=100, message='Username must be between 4 and 100 characters.'),
        Regexp(r'^[a-zA-Z0-9_]+$', message='Username can only contain letters, numbers, and underscores.')
    ])
    
    email = StringField('Email', validators=[
        DataRequired(message='Email is required.'),
        Email(message='Please enter a valid email address. (Example: name@domain.com)')
    ])
    
    password = PasswordField('Password', validators=[
        DataRequired(message='Password is required.'),
        Length(min=6, message='Password must be at least 6 characters long.'),
        Regexp(r'^(?=.*[A-Za-z])(?=.*\d)', message='Password must contain at least one letter and one number.')
    ])
    
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(message='Please confirm your password.'),
        EqualTo('password', message='Passwords must match.')
    ])
    
    full_name = StringField('Full Name', validators=[
        DataRequired(message='Full name is required.'),
        Length(min=2, max=100, message='Full name must be between 2 and 100 characters.')
    ])
    
    department = StringField('Department', validators=[
        DataRequired(message='Department is required.'),
        Length(max=100, message='Department name is too long.')
    ])
    
    role = SelectField('Role', choices=[
        ('student', 'Student'),
        ('faculty', 'Faculty')
    ], default='student', validators=[
        DataRequired(message='Please select a role.')
    ])
    
    email_notifications = BooleanField('Receive Email Notifications', default=True)
    
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Username already taken. Please choose a different username.')
    
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already registered. Please use a different email or login.')
        
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email.data):
            raise ValidationError('Please enter a valid email address. (Example: name@domain.com)')
        
        try:
            domain = email.data.split('@')[1]
            socket.gethostbyname(domain)
        except:
            raise ValidationError('Email domain does not exist. Please enter a valid email address.')
        
        fake_patterns = ['test', 'example', 'fake', 'dummy', 'temp', 'mailinator', 'guerrillamail']
        email_lower = email.data.lower()
        for pattern in fake_patterns:
            if pattern in email_lower:
                raise ValidationError('Please use a real email address. Temporary/fake emails are not allowed.')

class EventForm(FlaskForm):
    title = StringField('Event Title', validators=[
        DataRequired(message='Event title is required.'),
        Length(min=3, max=200, message='Title must be between 3 and 200 characters.')
    ])
    
    description = TextAreaField('Description', validators=[
        Length(max=2000, message='Description cannot exceed 2000 characters.')
    ])
    
    event_type = SelectField('Event Type', choices=[
        ('academic', 'Academic'),
        ('cultural', 'Cultural'),
        ('sports', 'Sports'),
        ('workshop', 'Workshop')
    ], validators=[
        DataRequired(message='Please select an event type.')
    ])
    
    venue = StringField('Venue', validators=[
        DataRequired(message='Venue is required.'),
        Length(max=200, message='Venue name is too long.')
    ])
    
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[
        DataRequired(message='Start date is required.')
    ])
    
    end_date = DateField('End Date', format='%Y-%m-%d')
    
    start_time = TimeField('Start Time', format='%H:%M', validators=[
        DataRequired(message='Start time is required.')
    ])
    
    end_time = TimeField('End Time', format='%H:%M', validators=[
        DataRequired(message='End time is required.')
    ])
    
    max_participants = IntegerField('Maximum Participants', default=100, validators=[
        DataRequired(message='Maximum participants is required.'),
        NumberRange(min=1, max=1000, message='Maximum participants must be between 1 and 1000.')
    ])
    
    submit = SubmitField('Create Event')
    
    def validate_start_date(self, start_date):
        from datetime import date
        if start_date.data < date.today():
            raise ValidationError('Start date cannot be in the past.')
    
    def validate_end_date(self, end_date):
        if end_date.data and self.start_date.data:
            if end_date.data < self.start_date.data:
                raise ValidationError('End date cannot be before start date.')
    
    def validate_end_time(self, end_time):
        if self.start_date.data == self.end_date.data:
            if self.start_time.data and end_time.data:
                if end_time.data <= self.start_time.data:
                    raise ValidationError('End time must be after start time.')