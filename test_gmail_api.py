import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

MAIL_USERNAME = os.getenv('MAIL_USERNAME')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')

print("=" * 60)
print("📧 Testing Gmail with New App Password")
print("=" * 60)
print(f"Username: {MAIL_USERNAME}")
print(f"Password: {'*' * 16}")
print("=" * 60)

# Create test email
msg = MIMEMultipart('alternative')
msg['Subject'] = "✅ Test Email - New App Password"
msg['From'] = MAIL_USERNAME
msg['To'] = MAIL_USERNAME

html = """
<html>
<body>
    <h1 style="color: #28a745;">✅ Test Successful!</h1>
    <p>Your new app password is working!</p>
    <p>🎉 Emails will now be sent from your app.</p>
</body>
</html>
"""

html_part = MIMEText(html, 'html')
msg.attach(html_part)

try:
    print("\n📧 Sending test email...")
    
    server = smtplib.SMTP('smtp.gmail.com', 587, timeout=30)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(MAIL_USERNAME, MAIL_PASSWORD)
    server.send_message(msg)
    server.quit()
    
    print(f"\n✅ Email sent successfully to {MAIL_USERNAME}")
    print("📬 Please check your inbox (including spam folder)")
    
except smtplib.SMTPAuthenticationError:
    print("\n❌ Authentication failed!")
    print("Please check:")
    print("  1. App password: emap wlrz vnrt slss (with spaces)")
    print("  2. 2-Step Verification is enabled in Google Account")
    print("  3. The app password is for 'Mail' and 'Other'")
    
except Exception as e:
    print(f"\n❌ Error: {str(e)}")