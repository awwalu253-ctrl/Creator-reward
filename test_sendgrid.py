import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# Get config
MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.sendgrid.net')
MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
MAIL_USERNAME = os.getenv('MAIL_USERNAME', 'apikey')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'awwalu253@gmail.com')

print("=" * 60)
print("📧 Testing SendGrid")
print("=" * 60)
print(f"Server: {MAIL_SERVER}")
print(f"Port: {MAIL_PORT}")
print(f"Username: {MAIL_USERNAME}")
print(f"Password: {'✅ SET' if MAIL_PASSWORD else '❌ NOT SET'}")
print(f"Password starts with SG.: {MAIL_PASSWORD.startswith('SG.') if MAIL_PASSWORD else False}")
print("=" * 60)

if not MAIL_PASSWORD:
    print("❌ MAIL_PASSWORD not set in .env")
    exit()

msg = MIMEMultipart('alternative')
msg['Subject'] = "✅ SendGrid Test"
msg['From'] = MAIL_DEFAULT_SENDER
msg['To'] = "awwalu253@gmail.com"

html = """
<html>
<body>
    <h1 style="color: #28a745;">✅ SendGrid Working!</h1>
    <p>Your email is configured correctly.</p>
</body>
</html>
"""
msg.attach(MIMEText(html, 'html'))

try:
    print("📧 Connecting to SendGrid...")
    server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=30)
    server.starttls()
    print("📧 Logging in...")
    server.login(MAIL_USERNAME, MAIL_PASSWORD)
    print("📧 Sending email...")
    server.send_message(msg)
    server.quit()
    print("✅ Email sent successfully!")
    print("📬 Check your inbox at awwalu253@gmail.com")
    
except smtplib.SMTPAuthenticationError as e:
    print(f"❌ Authentication failed: {e}")
    print("   Check your SendGrid API key")
except Exception as e:
    print(f"❌ Error: {e}")