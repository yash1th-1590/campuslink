import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'campuslink-secret-key-2024')
    
    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{os.getenv('MYSQL_USER')}:{os.getenv('MYSQL_PASSWORD')}@{os.getenv('MYSQL_HOST')}:{os.getenv('MYSQL_PORT')}/{os.getenv('MYSQL_DB')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    LOGIN_VIEW = 'login'
    
    # Server configuration
    SERVER_NAME = os.getenv('SERVER_NAME', '127.0.0.1:5000')
    
    # Email configuration
    EMAIL_FROM = os.getenv('EMAIL_FROM', 'noreply@campuslink.com')
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
    EMAIL_USER = os.getenv('EMAIL_USER', '')  
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')  
    
    

print(f"✅ Connecting to MySQL: {os.getenv('MYSQL_HOST')}:{os.getenv('MYSQL_PORT')}/{os.getenv('MYSQL_DB')}")
if os.getenv('EMAIL_USER'):
    print(f"✅ Email configured for: {os.getenv('EMAIL_USER')}")
else:
    print("⚠️ Email not configured - verification emails will be printed to console")