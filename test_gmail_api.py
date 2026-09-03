import os
import base64
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_gmail_service():
    creds = None
    
    # Try environment variables
    client_id = os.getenv('GMAIL_API_CLIENT_ID')
    client_secret = os.getenv('GMAIL_API_CLIENT_SECRET')
    refresh_token = os.getenv('GMAIL_API_REFRESH_TOKEN')
    
    print(f"📧 CLIENT_ID: {client_id[:30] if client_id else 'NOT SET'}...")
    print(f"📧 CLIENT_SECRET: {'✅' if client_secret else '❌'}")
    print(f"📧 REFRESH_TOKEN: {'✅' if refresh_token else '❌'}")
    
    if client_id and client_secret and refresh_token:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri='https://oauth2.googleapis.com/token',
            scopes=SCOPES
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if creds.valid:
            print("✅ Credentials from environment variables")
            return build('gmail', 'v1', credentials=creds)
    
    # Try token.pickle
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if creds.valid:
            print("✅ Credentials from token.pickle")
            return build('gmail', 'v1', credentials=creds)
    
    # Try credentials.json
    if os.path.exists('credentials.json'):
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=8080)
        if creds.valid:
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
            print("✅ Credentials from credentials.json")
            return build('gmail', 'v1', credentials=creds)
    
    print("❌ No credentials found")
    return None

def send_test_email():
    service = get_gmail_service()
    if not service:
        print("❌ No Gmail service")
        return
    
    try:
        message = MIMEMultipart('alternative')
        message['to'] = 'awwalu253@gmail.com'
        message['subject'] = '✅ Test Email - Gmail API'
        message['from'] = 'awwalu253@gmail.com'
        
        html = """
        <html>
        <body>
            <h1 style="color: #28a745;">✅ Test Successful!</h1>
            <p>Your Gmail API is working on localhost!</p>
        </body>
        </html>
        """
        html_part = MIMEText(html, 'html')
        message.attach(html_part)
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        
        print("✅ Test email sent successfully!")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == '__main__':
    send_test_email()