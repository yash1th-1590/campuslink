import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, url_for
import secrets

def send_verification_email(user_email, username, verification_token):
    """Send verification email to user"""
    try:
        
        server_name = current_app.config.get('SERVER_NAME', '127.0.0.1:5000')
        verification_url = f"http://{server_name}/verify/{verification_token}"
        
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
        msg['From'] = current_app.config.get('EMAIL_FROM', 'noreply@campuslink.com')
        msg['To'] = user_email
        
        part1 = MIMEText(text_content, 'plain')
        part2 = MIMEText(html_content, 'html')
        
        msg.attach(part1)
        msg.attach(part2)
        
        
        email_host = current_app.config.get('EMAIL_HOST')
        email_port = current_app.config.get('EMAIL_PORT')
        email_user = current_app.config.get('EMAIL_USER')
        email_password = current_app.config.get('EMAIL_PASSWORD')
        
     
        if not email_user or not email_password:
            print(f"\n⚠️ EMAIL NOT CONFIGURED - Would send to: {user_email}")
            print(f"   Link: {verification_url}")
            print("   To enable real emails, set EMAIL_USER and EMAIL_PASSWORD in .env file")
            print("=" * 50)
            return True
        
        
        try:
            server = smtplib.SMTP(email_host, email_port)
            server.starttls()
            server.login(email_user, email_password)
            server.send_message(msg)
            server.quit()
            print(f"\n✅ Verification email sent successfully to {user_email}")
            print("=" * 50)
            return True
        except Exception as smtp_error:
            print(f"\n❌ SMTP Error: {smtp_error}")
            print(f"   Failed to send to {user_email}")
            print(f"   Link would have been: {verification_url}")
            print("=" * 50)
            return False
            
    except Exception as e:
        print(f"Email error: {e}")
        return False