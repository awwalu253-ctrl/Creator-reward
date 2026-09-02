import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_oauth_tokens():
    """Get OAuth tokens for production"""
    if not os.path.exists('credentials.json'):
        print("❌ credentials.json not found!")
        print("Please place it in the project root.")
        return
    
    print("=" * 60)
    print("📧 Getting Gmail API Tokens")
    print("=" * 60)
    print("A browser window will open. Please sign in with:")
    print("📧 awwalu253@gmail.com")
    print("=" * 60)
    
    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json', SCOPES)
    creds = flow.run_local_server(port=8080)
    
    print("\n" + "=" * 60)
    print("✅ TOKENS GENERATED SUCCESSFULLY!")
    print("=" * 60)
    print("📝 FOR LOCAL DEVELOPMENT:")
    print("   token.pickle has been saved")
    print("\n📝 FOR RENDER PRODUCTION:")
    print("   Add these to your Render environment variables:")
    print("=" * 60)
    print(f"GMAIL_API_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_API_CLIENT_SECRET={creds.client_secret}")
    print(f"GMAIL_API_REFRESH_TOKEN={creds.refresh_token}")
    print("=" * 60)
    
    # Save token locally
    with open('token.pickle', 'wb') as token:
        pickle.dump(creds, token)
    print("\n✅ token.pickle saved for local use")

if __name__ == '__main__':
    get_oauth_tokens()