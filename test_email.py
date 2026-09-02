import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL = "awwalu253@gmail.com"
PASSWORD = "wkss kuwq mwaf oteb"

print("📧 Testing Gmail SSL (port 465)...")

msg = MIMEMultipart('alternative')
msg['Subject'] = "✅ Test Email"
msg['From'] = EMAIL
msg['To'] = EMAIL

html = """
<html>
<body>
    <h1 style="color: #28a745;">✅ Test Successful!</h1>
    <p>Your Gmail SSL is working!</p>
</body>
</html>
"""
msg.attach(MIMEText(html, 'html'))

try:
    server = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30)
    server.login(EMAIL, PASSWORD)
    server.send_message(msg)
    server.quit()
    print("✅ Email sent via SSL!")
    
except Exception as e:
    print(f"❌ Error: {e}")