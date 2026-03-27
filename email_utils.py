import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, url_for
import secrets

def send_verification_email(user_email, username, verification_token):
    """Send verification email to user"""
    try:
        # Build verification URL
        verification_url = f"http://{current_app.config['SERVER_NAME']}/verify/{verification_token}"
        
        subject = "Verify Your Email - CampusLink"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Arial, sans-serif;
                    background-color: #f4f4f4;
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    max-width: 550px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 16px;
                    padding: 40px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    padding-bottom: 20px;
                    border-bottom: 3px solid #6366f1;
                }}
                .header h1 {{
                    background: linear-gradient(135deg, #6366f1 0%, #ec489a 100%);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    margin: 0;
                    font-size: 28px;
                }}
                .content {{
                    padding: 30px 0;
                }}
                .button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #6366f1 0%, #ec489a 100%);
                    color: white;
                    padding: 14px 35px;
                    text-decoration: none;
                    border-radius: 50px;
                    margin: 20px 0;
                    font-weight: 600;
                }}
                .footer {{
                    text-align: center;
                    padding-top: 20px;
                    color: #666;
                    font-size: 12px;
                    border-top: 1px solid #eee;
                }}
                .note {{
                    background: #f8f9fa;
                    padding: 12px;
                    border-radius: 8px;
                    font-size: 12px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>CampusLink</h1>
                </div>
                <div class="content">
                    <h2>Welcome to CampusLink, {username}! 🎉</h2>
                    <p>Thank you for registering with us. Please verify your email address to complete your registration and start using CampusLink.</p>
                    <div style="text-align: center;">
                        <a href="{verification_url}" class="button">Verify Email Address</a>
                    </div>
                    <div class="note">
                        <p><strong>🔗 Verification Link:</strong></p>
                        <p style="word-break: break-all; color: #6366f1; font-size: 12px;">{verification_url}</p>
                        <p>⏰ This link will expire in <strong>24 hours</strong>.</p>
                    </div>
                    <p>If you did not create an account with CampusLink, please ignore this email.</p>
                </div>
                <div class="footer">
                    <p>&copy; 2024 CampusLink - Smart Real-Time Event Manager</p>
                    <p>Centralized Campus Event Management Platform</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Welcome to CampusLink, {username}!
        
        Thank you for registering. Please verify your email address by clicking the link below:
        
        {verification_url}
        
        This link will expire in 24 hours.
        
        If you did not create an account, please ignore this email.
        
        ---
        CampusLink - Smart Real-Time Event Manager
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = current_app.config['EMAIL_FROM']
        msg['To'] = user_email
        
        part1 = MIMEText(text_content, 'plain')
        part2 = MIMEText(html_content, 'html')
        
        msg.attach(part1)
        msg.attach(part2)
        
        # For development - just print (no actual email sending)
        print(f"\n📧 VERIFICATION EMAIL")
        print(f"   To: {user_email}")
        print(f"   Subject: {subject}")
        print(f"   Link: {verification_url}")
        print("=" * 50)
        
        # Uncomment below to actually send emails (requires SMTP setup)
        """
        server = smtplib.SMTP(current_app.config['EMAIL_HOST'], current_app.config['EMAIL_PORT'])
        server.starttls()
        server.login(current_app.config['EMAIL_USER'], current_app.config['EMAIL_PASSWORD'])
        server.send_message(msg)
        server.quit()
        """
        
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False