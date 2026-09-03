#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import pickle
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these SCOPES, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def main():
    """Shows basic usage of the Gmail API.
    Creates a token.pickle file for authentication.
    """
    creds = None
    
    # The file token.pickle stores the user's access and refresh tokens.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    # Print the refresh token
    if creds and creds.refresh_token:
        print("\n" + "=" * 60)
        print("✅ YOUR REFRESH TOKEN:")
        print("=" * 60)
        print(creds.refresh_token)
        print("=" * 60)
        print("\n📋 Copy this token and update your .env file:")
        print(f"GMAIL_API_REFRESH_TOKEN={creds.refresh_token}")
        print("=" * 60)
    else:
        print("❌ No refresh token found. Please try again.")
    
    # Test sending an email
    try:
        service = build('gmail', 'v1', credentials=creds)
        print("\n✅ Gmail API is working!")
        print("   Service created successfully.")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == '__main__':
    main()