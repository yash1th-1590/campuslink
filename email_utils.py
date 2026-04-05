import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
import secrets


def _send_email(to_email, subject, html_content, text_content):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = current_app.config.get('EMAIL_FROM', 'noreply@campuslink.com')
    msg['To'] = to_email
    msg.attach(MIMEText(text_content, 'plain'))
    msg.attach(MIMEText(html_content, 'html'))

    email_host = current_app.config.get('EMAIL_HOST')
    email_port = current_app.config.get('EMAIL_PORT')
    email_user = current_app.config.get('EMAIL_USER')
    email_password = current_app.config.get('EMAIL_PASSWORD')

    if not email_user or not email_password:
        print(f"\n⚠️  EMAIL NOT CONFIGURED - Would send to: {to_email}")
        print(f"   Subject: {subject}")
        print("=" * 50)
        return True
    try:
        server = smtplib.SMTP(email_host, email_port)
        server.starttls()
        server.login(email_user, email_password)
        server.send_message(msg)
        server.quit()
        print(f"\n✅ Email sent to {to_email}")
        return True
    except Exception as smtp_error:
        print(f"\n❌ SMTP Error: {smtp_error}")
        return False


def _base_template(body_html):
    return f"""
    <!DOCTYPE html><html><head><style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px; }}
        .container {{ max-width: 550px; margin: 0 auto; background: white; border-radius: 16px;
                     padding: 40px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; padding-bottom: 20px; border-bottom: 3px solid #6366f1; }}
        .header h1 {{ background: linear-gradient(135deg, #6366f1 0%, #ec489a 100%);
                      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                      margin: 0; font-size: 28px; }}
        .content {{ padding: 30px 0; }}
        .button {{ display: inline-block; background: linear-gradient(135deg, #6366f1 0%, #ec489a 100%);
                   color: white; padding: 14px 35px; text-decoration: none; border-radius: 50px;
                   margin: 20px 0; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; color: #666; font-size: 12px; border-top: 1px solid #eee; }}
        .note {{ background: #f8f9fa; padding: 12px; border-radius: 8px; font-size: 12px; color: #666; }}
        .badge-green {{ background: #d1fae5; color: #065f46; padding: 4px 12px; border-radius: 20px; font-weight: 600; }}
        .badge-red {{ background: #fee2e2; color: #991b1b; padding: 4px 12px; border-radius: 20px; font-weight: 600; }}
        .badge-yellow {{ background: #fef9c3; color: #713f12; padding: 4px 12px; border-radius: 20px; font-weight: 600; }}
    </style></head><body>
        <div class="container">
            <div class="header"><h1>CampusLink</h1></div>
            <div class="content">{body_html}</div>
            <div class="footer"><p>&copy; 2024 CampusLink - Smart Real-Time Event Manager</p></div>
        </div>
    </body></html>"""


def send_verification_email(user_email, username, verification_token):
    server_name = current_app.config.get('SERVER_NAME', '127.0.0.1:5000')
    verification_url = f"http://{server_name}/verify/{verification_token}"
    body = f"""
        <h2>Welcome to CampusLink, {username}! 🎉</h2>
        <p>Please verify your email to complete registration.</p>
        <div style="text-align: center;">
            <a href="{verification_url}" class="button">Verify Email Address</a>
        </div>
        <div class="note">
            <p><strong>🔗 Link:</strong></p>
            <p style="word-break: break-all; color: #6366f1;">{verification_url}</p>
            <p>⏰ Expires in <strong>24 hours</strong>.</p>
        </div>
        <p>If you did not create this account, ignore this email.</p>"""
    text = f"Welcome {username}!\nVerify: {verification_url}\nExpires in 24 hours."
    return _send_email(user_email, "Verify Your Email - CampusLink", _base_template(body), text)


def send_coordinator_application_email(admin_email, applicant_name, applicant_username, reason, review_url):
    body = f"""
        <h2>📋 New Student Coordinator Application</h2>
        <p><strong>{applicant_name}</strong> (@{applicant_username}) has applied to become a Student Coordinator.</p>
        <div class="note"><p><strong>Reason:</strong></p><p><em>"{reason}"</em></p></div>
        <div style="text-align:center;"><a href="{review_url}" class="button">Review Application</a></div>"""
    text = f"New coordinator application from {applicant_name}.\nReason: {reason}\nReview: {review_url}"
    return _send_email(admin_email, f"Coordinator Application - {applicant_name}", _base_template(body), text)


def send_coordinator_decision_email(user_email, username, approved, revoked=False):
    if revoked:
        subject = "Student Coordinator Role Revoked - CampusLink"
        body = f"<h2>Update, {username}</h2><p>Your <span class='badge-red'>Student Coordinator</span> role has been <strong>revoked</strong> by admin.</p>"
        text = f"Hi {username}, your Student Coordinator role has been revoked."
    elif approved:
        subject = "Coordinator Application Approved! - CampusLink"
        body = f"<h2>Congratulations, {username}! 🎉</h2><p>Your application has been <span class='badge-green'>Approved</span>! You can now create and manage events.</p>"
        text = f"Hi {username}, your coordinator application has been approved!"
    else:
        subject = "Coordinator Application Update - CampusLink"
        body = f"<h2>Application Update, {username}</h2><p>Your application was <span class='badge-red'>Not Approved</span> at this time. You may apply again later.</p>"
        text = f"Hi {username}, your coordinator application was not approved."
    return _send_email(user_email, subject, _base_template(body), text)


def send_event_update_email(user_email, username, event_title, changes_summary, event_url):
    changes_html = "".join([f"<li>{c}</li>" for c in changes_summary])
    body = f"""
        <h2>📢 Event Updated: {event_title}</h2>
        <p>Hi {username}, an event you are registered for has been updated.</p>
        <div class="note"><p><strong>What changed:</strong></p><ul>{changes_html}</ul></div>
        <div style="text-align:center;"><a href="{event_url}" class="button">View Event Details</a></div>"""
    text = f"Event '{event_title}' updated.\nChanges:\n" + "\n".join(f"- {c}" for c in changes_summary)
    return _send_email(user_email, f"Event Updated: {event_title}", _base_template(body), text)


def send_payment_receipt_email(organizer_email, organizer_name, student_name,
                                event_title, event_url):
    """Notify organizer that a student has submitted a payment receipt."""
    body = f"""
        <h2>💳 Payment Receipt Submitted</h2>
        <p>Hi {organizer_name},</p>
        <p><strong>{student_name}</strong> has submitted a payment receipt for
        <strong>"{event_title}"</strong> and is awaiting verification.</p>
        <div style="text-align:center;">
            <a href="{event_url}" class="button">Review Receipt</a>
        </div>"""
    text = f"{student_name} submitted receipt for '{event_title}'. Review at: {event_url}"
    return _send_email(organizer_email, f"Receipt Submitted - {event_title}", _base_template(body), text)


def send_payment_approved_email(student_email, student_name, event_title, event_url):
    """Notify student their payment was approved."""
    body = f"""
        <h2>✅ Payment Approved!</h2>
        <p>Hi {student_name},</p>
        <p>Your payment for <strong>"{event_title}"</strong> has been
        <span class="badge-green">Approved</span>!</p>
        <p>Your registration is now <strong>confirmed</strong>. See you at the event!</p>
        <div style="text-align:center;">
            <a href="{event_url}" class="button">View Event</a>
        </div>"""
    text = f"Hi {student_name}, your payment for '{event_title}' has been approved! Registration confirmed."
    return _send_email(student_email, f"Payment Approved - {event_title}", _base_template(body), text)


def send_payment_rejected_email(student_email, student_name, event_title, rejection_note, event_url):
    """Notify student their payment was rejected."""
    note_html = f"<div class='note'><strong>Reason:</strong> {rejection_note}</div>" if rejection_note else ""
    body = f"""
        <h2>❌ Payment Not Verified</h2>
        <p>Hi {student_name},</p>
        <p>Your payment receipt for <strong>"{event_title}"</strong> was
        <span class="badge-red">Rejected</span>.</p>
        {note_html}
        <p>You can re-upload a correct receipt to complete your registration.</p>
        <div style="text-align:center;">
            <a href="{event_url}" class="button">Re-upload Receipt</a>
        </div>"""
    text = f"Hi {student_name}, your receipt for '{event_title}' was rejected. Reason: {rejection_note or 'N/A'}. Re-upload at: {event_url}"
    return _send_email(student_email, f"Payment Rejected - {event_title}", _base_template(body), text)