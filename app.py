#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import io
import uuid
import datetime
import re
import secrets
import json
import threading
import time
import base64
import pickle
import csv
import random
import string
from io import StringIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import requests
import logging
from logging.handlers import RotatingFileHandler

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# SSL imports for production
import certifi
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

# ============================================================
# CONFIGURATION
# ============================================================

# Supabase config
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Paystack config
PAYSTACK_PUBLIC = os.getenv('PAYSTACK_PUBLIC_KEY')
PAYSTACK_SECRET = os.getenv('PAYSTACK_SECRET_KEY')
PAYSTACK_CALLBACK = os.getenv('PAYSTACK_CALLBACK_URL', 'https://your-app.onrender.com/payment/callback')

# Gmail API Scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Company config
COMPANY_NAME = os.getenv('COMPANY_NAME', 'Creator Rewards')
COMPANY_EMAIL = os.getenv('COMPANY_EMAIL', 'support@creatorrewards.com')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'juwon20092006@gmail.com')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
CAMPAIGN_NAME = os.getenv('CAMPAIGN_NAME', 'YouTube Creator Gift Box 2026')
REWARD_NAME = os.getenv('REWARD_NAME', 'Creator Gift Package')
CLAIM_CODE = os.getenv('CLAIM_CODE', 'YT-GIFT-2026-VIP')

# Email config - using Gmail API or SMTP
MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
MAIL_USERNAME = os.getenv('MAIL_USERNAME')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@creatorrewards.com')

# SSL verification for production
VERIFY_SSL = certifi.where() if os.getenv('FLASK_ENV') == 'production' else False

# Setup logging
if not os.path.exists('logs'):
    os.mkdir('logs')
file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

# ============================================================
# GMAIL API HELPER FUNCTIONS
# ============================================================
def get_gmail_service():
    """Get authenticated Gmail API service"""
    creds = None
    
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                app.logger.error("credentials.json not found!")
                return None
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return build('gmail', 'v1', credentials=creds)

def send_email_via_api(recipient, subject, html_content, plain_text_content=None):
    """Send email using Gmail API"""
    try:
        service = get_gmail_service()
        if not service:
            return False
        
        message = MIMEMultipart('alternative')
        message['to'] = recipient
        message['subject'] = subject
        message['from'] = f"{COMPANY_NAME} <{MAIL_DEFAULT_SENDER}>"
        message['reply-to'] = COMPANY_EMAIL
        
        if plain_text_content:
            text_part = MIMEText(plain_text_content, 'plain')
            message.attach(text_part)
        
        html_part = MIMEText(html_content, 'html')
        message.attach(html_part)
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        
        return True
        
    except Exception as e:
        app.logger.error(f"Gmail API error: {str(e)}")
        return False

def send_email_via_smtp(recipient, subject, html_content, plain_text_content=None):
    """Send email via SMTP (fallback for production)"""
    try:
        if not MAIL_USERNAME or not MAIL_PASSWORD:
            app.logger.warning("SMTP not configured")
            return False
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{COMPANY_NAME} <{MAIL_DEFAULT_SENDER}>"
        msg['To'] = recipient
        msg['Reply-To'] = COMPANY_EMAIL
        
        if plain_text_content:
            text_part = MIMEText(plain_text_content, 'plain')
            msg.attach(text_part)
        
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=30)
        if MAIL_USE_TLS:
            server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        app.logger.info(f"✅ Email sent via SMTP to {recipient}")
        return True
        
    except Exception as e:
        app.logger.error(f"SMTP error: {str(e)}")
        return False

# ============================================================
# SUPABASE HELPERS WITH SSL FIX
# ============================================================
def supabase_select(table, filters=None, order_by=None, limit=None):
    """Select data from Supabase"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {'error': 'Supabase not configured'}
    
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    params = {}
    if filters:
        for key, value in filters.items():
            params[key] = f"eq.{value}"
    if order_by:
        params['order'] = order_by
    if limit:
        params['limit'] = limit
    
    try:
        app.logger.info(f"📡 Selecting from {table}")
        response = requests.get(url, headers=headers, params=params, timeout=30, verify=VERIFY_SSL)
        app.logger.info(f"📡 Response status: {response.status_code}")
        
        if response.status_code == 200:
            return response.json()
        else:
            app.logger.error(f"❌ Select error: {response.text}")
            return {'error': f'HTTP {response.status_code}', 'detail': response.text}
    except Exception as e:
        app.logger.error(f"❌ Select error: {str(e)}")
        return {'error': str(e)}

def supabase_insert(table, data):
    """Insert data into Supabase"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {'error': 'Supabase not configured'}
    
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        app.logger.info(f"📡 Inserting into {table}")
        response = requests.post(url, headers=headers, json=data, timeout=30, verify=VERIFY_SSL)
        app.logger.info(f"📡 Response status: {response.status_code}")
        
        if response.status_code in [200, 201]:
            result = response.json()
            app.logger.info(f"✅ Insert successful")
            return result
        else:
            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            app.logger.error(f"❌ Insert failed: {error_msg}")
            return {'error': error_msg, 'detail': response.text}
            
    except Exception as e:
        app.logger.error(f"❌ Insert error: {str(e)}")
        return {'error': str(e)}

def supabase_update(table, data, filters):
    """Update data in Supabase"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {'error': 'Supabase not configured'}
    
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    params = {}
    for key, value in filters.items():
        params[key] = f"eq.{value}"
    
    try:
        app.logger.info(f"📡 Updating {table}")
        response = requests.patch(url, headers=headers, params=params, json=data, timeout=30, verify=VERIFY_SSL)
        app.logger.info(f"📡 Response status: {response.status_code}")
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            app.logger.error(f"❌ Update error: {response.text}")
            return {'error': f'HTTP {response.status_code}', 'detail': response.text}
    except Exception as e:
        app.logger.error(f"❌ Update error: {str(e)}")
        return {'error': str(e)}

# ============================================================
# CLAIM CODE GENERATION
# ============================================================
def generate_unique_code():
    """Generate a unique claim code"""
    max_attempts = 50
    
    for _ in range(max_attempts):
        parts = [
            ''.join(random.choices(string.ascii_uppercase, k=3)),
            ''.join(random.choices(string.ascii_uppercase + string.digits, k=5)),
            ''.join(random.choices(string.ascii_uppercase, k=3))
        ]
        code = '-'.join(parts)
        
        existing = supabase_select('claim_codes', {'code': code})
        if not existing or (isinstance(existing, dict) and 'error' in existing) or len(existing) == 0:
            return code
    
    timestamp = datetime.datetime.now().strftime('%y%m%d%H%M%S')
    return f"CODE-{timestamp}-{random.randint(1000, 9999)}"

def generate_bulk_codes(count):
    """Generate multiple unique codes"""
    codes = []
    for i in range(count):
        code = generate_unique_code()
        if code:
            codes.append({
                'code': code,
                'status': 'active',
                'created_at': datetime.datetime.now().isoformat(),
                'created_by': 'admin'
            })
    return codes

# ============================================================
# EMAIL SYSTEM
# ============================================================
def send_email(recipient, subject, template_name, **kwargs):
    """Send email using Gmail API or SMTP fallback"""
    try:
        with app.app_context():
            html_content = render_template(f'emails/{template_name}.html', **kwargs)
        
        claim = kwargs.get('claim', {})
        plain_text = f"""
{subject}

Claim Number: {claim.get('claim_number', 'N/A')}
Name: {claim.get('full_name', 'N/A')}
Email: {claim.get('email', 'N/A')}
Channel: {claim.get('channel_name', 'N/A')}

This is an automated message from {COMPANY_NAME}.

For support: {COMPANY_EMAIL}
        """
        
        app.logger.info(f"Sending email to {recipient}")
        
        # Try Gmail API first
        if os.path.exists('credentials.json') and os.path.exists('token.pickle'):
            if send_email_via_api(recipient, subject, html_content, plain_text):
                return True
        
        # Try SMTP as fallback
        if MAIL_USERNAME and MAIL_PASSWORD:
            if send_email_via_smtp(recipient, subject, html_content, plain_text):
                return True
        
        # Fallback: save to file
        return send_email_to_file(recipient, subject, template_name, **kwargs)
        
    except Exception as e:
        app.logger.error(f"Email error: {str(e)}")
        return send_email_to_file(recipient, subject, template_name, **kwargs)

def send_email_to_file(recipient, subject, template_name, **kwargs):
    """Save email to file as fallback"""
    try:
        with app.app_context():
            html_content = render_template(f'emails/{template_name}.html', **kwargs)
        
        if not os.path.exists('emails_sent'):
            os.mkdir('emails_sent')
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_recipient = re.sub(r'[^a-zA-Z0-9]', '_', recipient)
        filename = f"emails_sent/{timestamp}_{safe_recipient}_{template_name}.html"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        app.logger.info(f"Email saved to: {filename}")
        return True
        
    except Exception as e:
        app.logger.error(f"Failed to save email: {str(e)}")
        return False

def send_claim_confirmation(claim_data):
    payment_url = f"{os.getenv('PAYSTACK_CALLBACK_URL', 'http://localhost:5000').replace('/payment/callback', '')}/payment/{claim_data['id']}"
    
    return send_email(
        recipient=claim_data['email'],
        subject=f"🎁 Your Gift Claim Confirmation - {claim_data['claim_number']}",
        template_name='claim_confirmation',
        claim=claim_data,
        payment_url=payment_url,
        company_name=COMPANY_NAME,
        campaign_name=CAMPAIGN_NAME,
        reward_name=REWARD_NAME,
        claim_code=CLAIM_CODE,
        current_year=datetime.datetime.now().year
    )

def send_admin_notification(claim_data):
    return send_email(
        recipient=ADMIN_EMAIL,
        subject=f"📋 New Gift Claim Submitted - {claim_data['claim_number']}",
        template_name='admin_notification',
        claim=claim_data,
        company_name=COMPANY_NAME,
        reward_name=REWARD_NAME,
        current_year=datetime.datetime.now().year
    )

def send_payment_receipt(claim_data, payment_data):
    return send_email(
        recipient=claim_data['email'],
        subject=f"✅ Payment Confirmed - {claim_data['claim_number']}",
        template_name='payment_receipt',
        claim=claim_data,
        payment=payment_data,
        company_name=COMPANY_NAME,
        reward_name=REWARD_NAME,
        current_year=datetime.datetime.now().year
    )

def send_payment_failed(claim_data, error_message=None):
    payment_url = f"{os.getenv('PAYSTACK_CALLBACK_URL', 'http://localhost:5000').replace('/payment/callback', '')}/payment/{claim_data['id']}"
    
    return send_email(
        recipient=claim_data['email'],
        subject=f"❌ Payment Failed - {claim_data['claim_number']}",
        template_name='payment_failed',
        claim=claim_data,
        payment_url=payment_url,
        error_message=error_message,
        company_name=COMPANY_NAME,
        reward_name=REWARD_NAME,
        current_year=datetime.datetime.now().year
    )

# ============================================================
# ADMIN AUTHENTICATION
# ============================================================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('Please login as admin first', 'warning')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================================
# UTILITY FUNCTIONS
# ============================================================
def generate_claim_number():
    year = datetime.datetime.now().year
    
    try:
        result = supabase_select('gift_claims', order_by='updated_at.desc', limit=1)
        
        if result and isinstance(result, list) and len(result) > 0:
            last_claim = result[0]
            last_number = last_claim.get('claim_number', '')
            if last_number and len(last_number) > 10:
                parts = last_number.split('-')
                if len(parts) >= 3:
                    last_part = parts[-1]
                    if last_part.isdigit():
                        last_num = int(last_part)
                        new_num = last_num + 1
                        claim_number = f"GC-{year}-{new_num:04d}"
                        
                        check = supabase_select('gift_claims', filters={'claim_number': claim_number})
                        if check and isinstance(check, list) and len(check) == 0:
                            return claim_number
    except Exception as e:
        app.logger.error(f"Error generating claim number: {str(e)}")
    
    import random
    for _ in range(10):
        random_num = random.randint(1000, 9999)
        claim_number = f"GC-{year}-{random_num:04d}"
        check = supabase_select('gift_claims', filters={'claim_number': claim_number})
        if check and isinstance(check, list) and len(check) == 0:
            return claim_number
    
    return f"GC-{year}-{uuid.uuid4().hex[:4].upper()}"

def generate_payment_reference():
    return f"PAY-{datetime.datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    phone = re.sub(r'[\s\-\(\)\+]', '', phone)
    return len(phone) >= 10 and phone.isdigit()

# ============================================================
# ROUTES - PUBLIC
# ============================================================
@app.route('/')
def landing():
    return render_template('landing.html', 
                         company_name=COMPANY_NAME,
                         campaign_name=CAMPAIGN_NAME,
                         reward_name=REWARD_NAME,
                         current_year=datetime.datetime.now().year)

@app.route('/claim', methods=['GET', 'POST'])
def claim_form():
    if request.method == 'GET':
        return render_template('claim_form.html',
                             company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME,
                             reward_name=REWARD_NAME,
                             claim_code=CLAIM_CODE)
    
    data = request.form
    app.logger.info(f"📝 Form data received: {dict(data)}")
    
    required = ['full_name', 'email', 'channel_name', 'phone', 'country', 'address', 'city', 'postal_code', 'clothing_size', 'claim_code']
    for field in required:
        if not data.get(field, '').strip():
            flash(f'Please fill in {field.replace("_", " ")}', 'error')
            return render_template('claim_form.html', company_name=COMPANY_NAME,
                                 campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME,
                                 claim_code=CLAIM_CODE, form_data=data)
    
    if not validate_email(data['email']):
        flash('Please enter a valid email address', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME,
                             claim_code=CLAIM_CODE, form_data=data)
    
    if not validate_phone(data['phone']):
        flash('Please enter a valid phone number', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME,
                             claim_code=CLAIM_CODE, form_data=data)
    
    # Validate claim code
    claim_code_id = None
    code_data = None
    
    if data.get('claim_code'):
        code_result = supabase_select('claim_codes', {'code': data['claim_code'].upper()})
        
        if not code_result or (isinstance(code_result, dict) and 'error' in code_result) or len(code_result) == 0:
            flash('Invalid claim code. Please check your code and try again.', 'error')
            return render_template('claim_form.html', company_name=COMPANY_NAME,
                                 campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME,
                                 claim_code=CLAIM_CODE, form_data=data)
        
        code_data = code_result[0]
        
        if code_data.get('status') != 'active':
            flash('This claim code has already been used or expired.', 'error')
            return render_template('claim_form.html', company_name=COMPANY_NAME,
                                 campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME,
                                 claim_code=CLAIM_CODE, form_data=data)
        
        if code_data.get('expires_at'):
            try:
                expires_at = datetime.datetime.fromisoformat(code_data['expires_at'].replace('Z', '+00:00'))
                if expires_at < datetime.datetime.now(expires_at.tzinfo):
                    supabase_update('claim_codes', {'status': 'expired'}, {'id': code_data['id']})
                    flash('This claim code has expired.', 'error')
                    return render_template('claim_form.html', company_name=COMPANY_NAME,
                                         campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME,
                                         claim_code=CLAIM_CODE, form_data=data)
            except Exception as e:
                app.logger.error(f"Error checking expiry: {str(e)}")
        
        if code_data.get('max_uses', 1) <= code_data.get('current_uses', 0):
            flash('This claim code has reached its maximum uses.', 'error')
            return render_template('claim_form.html', company_name=COMPANY_NAME,
                                 campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME,
                                 claim_code=CLAIM_CODE, form_data=data)
        
        claim_code_id = code_data['id']
    else:
        flash('Please enter a claim code.', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME,
                             claim_code=CLAIM_CODE, form_data=data)
    
    claim_number = generate_claim_number()
    app.logger.info(f"🔢 Generated claim number: {claim_number}")
    
    claim_data = {
        'claim_number': claim_number,
        'full_name': data['full_name'].strip(),
        'email': data['email'].strip().lower(),
        'channel_name': data['channel_name'].strip(),
        'channel_url': data.get('channel_url', '').strip(),
        'phone': data['phone'].strip(),
        'country': data['country'].strip(),
        'address': data['address'].strip(),
        'city': data['city'].strip(),
        'postal_code': data['postal_code'].strip(),
        'clothing_size': data['clothing_size'].strip(),
        'claim_code': data['claim_code'].strip().upper(),
        'status': 'pending',
        'shipping_fee_paid': 'false',
        'claim_date': datetime.datetime.now().isoformat(),
        'updated_at': datetime.datetime.now().isoformat()
    }
    
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            flash('Database not configured. Please check your .env file.', 'error')
            return render_template('claim_form.html', company_name=COMPANY_NAME,
                                 campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME,
                                 claim_code=CLAIM_CODE, form_data=data)
        
        result = supabase_insert('gift_claims', claim_data)
        
        if isinstance(result, dict) and 'error' in result:
            flash('Database error. Please try again.', 'error')
            return render_template('claim_form.html', company_name=COMPANY_NAME,
                                 campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME,
                                 claim_code=CLAIM_CODE, form_data=data)
        
        if result and isinstance(result, list) and len(result) > 0:
            claim_id = result[0]['id']
        else:
            claim_id = str(uuid.uuid4())
        
        claim_data['id'] = claim_id
        
        if claim_code_id and code_data:
            supabase_update('claim_codes', {
                'status': 'used',
                'used_by_claim_id': claim_id,
                'used_at': datetime.datetime.now().isoformat(),
                'current_uses': code_data.get('current_uses', 0) + 1
            }, {'id': claim_code_id})
        
        session['claim_id'] = claim_id
        session['claim_number'] = claim_number
        
        def send_emails_in_background():
            with app.app_context():
                try:
                    send_claim_confirmation(claim_data)
                    send_admin_notification(claim_data)
                    app.logger.info(f"✅ Emails sent for claim {claim_number}")
                except Exception as e:
                    app.logger.error(f"❌ Background email error: {str(e)}")
        
        email_thread = threading.Thread(target=send_emails_in_background, daemon=True)
        email_thread.start()
        
        flash('Your gift claim has been submitted successfully!', 'success')
        return redirect(url_for('review_claim', claim_id=claim_id))
        
    except Exception as e:
        app.logger.error(f"❌ Exception in claim submission: {str(e)}", exc_info=True)
        flash('An error occurred. Please try again.', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME,
                             claim_code=CLAIM_CODE, form_data=data)

@app.route('/review/<claim_id>')
def review_claim(claim_id):
    result = supabase_select('gift_claims', {'id': claim_id})
    
    if not result or (isinstance(result, dict) and 'error' in result):
        flash('Claim not found.', 'error')
        return redirect(url_for('claim_form'))
    
    claim = result[0] if isinstance(result, list) else result
    
    return render_template('review.html',
                         claim=claim,
                         shipping_fee=120.00,
                         currency='USD',
                         company_name=COMPANY_NAME,
                         company_email=COMPANY_EMAIL,
                         campaign_name=CAMPAIGN_NAME,
                         reward_name=REWARD_NAME)

@app.route('/payment/<claim_id>')
def initiate_payment(claim_id):
    try:
        result = supabase_select('gift_claims', {'id': claim_id})
        
        if not result or (isinstance(result, dict) and 'error' in result):
            flash('Claim not found.', 'error')
            return redirect(url_for('landing'))
        
        claim = result[0] if isinstance(result, list) else result
        
        if claim.get('shipping_fee_paid') == 'true':
            flash('Shipping fee already paid.', 'info')
            return redirect(url_for('confirmation', claim_id=claim_id))
        
        if not PAYSTACK_SECRET:
            flash('Payment system is not configured. Please contact support.', 'error')
            return redirect(url_for('review_claim', claim_id=claim_id))
        
        payment_ref = generate_payment_reference()
        
        supabase_update('gift_claims', {
            'payment_reference': payment_ref,
            'status': 'payment_pending',
            'updated_at': datetime.datetime.now().isoformat()
        }, {'id': claim_id})
        
        usd_amount = 120.00
        exchange_rate = 1500
        ngn_amount = usd_amount * exchange_rate
        amount_in_kobo = int(ngn_amount * 100)
        
        paystack_data = {
            'email': claim['email'],
            'amount': amount_in_kobo,
            'currency': 'NGN',
            'reference': payment_ref,
            'callback_url': PAYSTACK_CALLBACK,
            'metadata': {
                'claim_id': claim_id,
                'claim_number': claim['claim_number'],
                'customer_name': claim['full_name'],
                'usd_amount': usd_amount,
                'exchange_rate': exchange_rate
            }
        }
        
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=paystack_data, headers=headers, timeout=30)
        response_data = response.json()
        
        if response_data['status']:
            return redirect(response_data['data']['authorization_url'])
        else:
            app.logger.error(f"Paystack error: {response_data}")
            flash(f'Payment error: {response_data.get("message", "Please try again")}', 'error')
            return redirect(url_for('review_claim', claim_id=claim_id))
            
    except Exception as e:
        app.logger.error(f"Payment error: {str(e)}")
        flash('Payment error. Please try again.', 'error')
        return redirect(url_for('review_claim', claim_id=claim_id))

@app.route('/payment/callback')
def payment_callback():
    reference = request.args.get('reference') or request.args.get('trxref')
    
    if not reference:
        flash('Payment reference missing.', 'error')
        return redirect(url_for('landing'))
    
    app.logger.info(f"📡 Payment callback received with reference: {reference}")
    
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        data = response.json()
        
        if data['status'] and data['data']['status'] == 'success':
            metadata = data['data'].get('metadata', {})
            claim_id_from_metadata = metadata.get('claim_id')
            
            claim = None
            claim_id = None
            
            if claim_id_from_metadata:
                result = supabase_select('gift_claims', {'id': claim_id_from_metadata})
                if result and isinstance(result, list) and len(result) > 0:
                    claim = result[0]
                    claim_id = claim_id_from_metadata
            
            if not claim:
                result = supabase_select('gift_claims', {'payment_reference': reference})
                if result and isinstance(result, list) and len(result) > 0:
                    claim = result[0]
                    claim_id = claim['id']
            
            if claim and claim_id:
                supabase_update('gift_claims', {
                    'status': 'paid',
                    'shipping_fee_paid': 'true',
                    'updated_at': datetime.datetime.now().isoformat()
                }, {'id': claim_id})
                
                payment_data = {
                    'claim_id': claim_id,
                    'transaction_id': data['data']['reference'],
                    'amount': data['data']['amount'] / 100,
                    'currency': data['data']['currency'],
                    'paystack_reference': data['data']['reference'],
                    'status': 'success',
                    'payment_date': datetime.datetime.now().isoformat()
                }
                supabase_insert('payments', payment_data)
                
                def send_receipt_in_background():
                    with app.app_context():
                        try:
                            send_payment_receipt(claim, payment_data)
                            app.logger.info(f"✅ Payment receipt sent for {claim['claim_number']}")
                        except Exception as e:
                            app.logger.error(f"❌ Receipt email error: {str(e)}")
                
                email_thread = threading.Thread(target=send_receipt_in_background, daemon=True)
                email_thread.start()
                
                flash('Payment successful! Your gift package is being prepared.', 'success')
                return redirect(url_for('confirmation', claim_id=claim_id))
            else:
                flash('Claim not found for this payment. Please contact support.', 'error')
                return redirect(url_for('landing'))
        else:
            flash('Payment verification failed. Please try again.', 'error')
            return redirect(url_for('landing'))
            
    except Exception as e:
        app.logger.error(f"❌ Callback error: {str(e)}", exc_info=True)
        flash('Payment verification error. Please contact support.', 'error')
        return redirect(url_for('landing'))

@app.route('/webhook/paystack', methods=['POST'])
def paystack_webhook():
    try:
        event_data = request.get_json()
        event = event_data.get('event')
        
        if event == 'charge.success':
            data = event_data.get('data', {})
            reference = data.get('reference')
            
            if reference:
                result = supabase_select('gift_claims', {'payment_reference': reference})
                
                if result and isinstance(result, list) and len(result) > 0:
                    claim = result[0]
                    claim_id = claim['id']
                    
                    supabase_update('gift_claims', {
                        'status': 'paid',
                        'shipping_fee_paid': 'true',
                        'updated_at': datetime.datetime.now().isoformat()
                    }, {'id': claim_id})
                    
                    payment_data = {
                        'claim_id': claim_id,
                        'transaction_id': data.get('reference'),
                        'amount': data.get('amount', 0) / 100,
                        'currency': data.get('currency', 'NGN'),
                        'paystack_reference': data.get('reference'),
                        'status': 'success',
                        'payment_date': datetime.datetime.now().isoformat()
                    }
                    supabase_insert('payments', payment_data)
        
        return '', 200
        
    except Exception as e:
        app.logger.error(f"Webhook error: {str(e)}")
        return '', 200

@app.route('/confirmation/<claim_id>')
def confirmation(claim_id):
    result = supabase_select('gift_claims', {'id': claim_id})
    
    if not result or (isinstance(result, dict) and 'error' in result):
        flash('Claim not found.', 'error')
        return redirect(url_for('landing'))
    
    claim = result[0] if isinstance(result, list) else result
    
    return render_template('confirmation.html',
                         claim=claim,
                         company_name=COMPANY_NAME,
                         company_email=COMPANY_EMAIL,
                         campaign_name=CAMPAIGN_NAME,
                         reward_name=REWARD_NAME,
                         current_year=datetime.datetime.now().year)

@app.route('/terms')
def terms():
    return render_template('terms.html',
                         company_name=COMPANY_NAME,
                         campaign_name=CAMPAIGN_NAME,
                         current_year=datetime.datetime.now().year)

@app.route('/privacy')
def privacy():
    return render_template('privacy.html',
                         company_name=COMPANY_NAME,
                         campaign_name=CAMPAIGN_NAME,
                         company_email=COMPANY_EMAIL,
                         current_year=datetime.datetime.now().year)

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'supabase_configured': bool(SUPABASE_URL and SUPABASE_KEY),
        'paystack_configured': bool(PAYSTACK_SECRET),
        'gmail_api_configured': os.path.exists('credentials.json'),
        'gmail_api_authenticated': os.path.exists('token.pickle'),
        'smtp_configured': bool(MAIL_USERNAME and MAIL_PASSWORD),
        'timestamp': datetime.datetime.now().isoformat()
    })

# ============================================================
# ROUTES - ADMIN
# ============================================================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            flash('Welcome Admin!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid password', 'error')
    return render_template('admin/login.html', company_name=COMPANY_NAME)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Logged out successfully', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    try:
        now = datetime.datetime.now()
        
        claims_result = supabase_select('gift_claims', order_by='updated_at.desc')
        
        if claims_result and isinstance(claims_result, list):
            claims = claims_result
        else:
            claims = []
        
        total_claims = len(claims)
        total_paid = 0
        total_pending = 0
        total_shipped = 0
        total_delivered = 0
        total_cancelled = 0
        total_revenue = 0.0
        payment_paid = 0
        payment_unpaid = 0
        
        size_distribution = {'S': 0, 'M': 0, 'L': 0, 'XL': 0, '2XL': 0, '3XL': 0}
        country_distribution = {}
        
        for claim in claims:
            status = claim.get('status', 'pending')
            if status == 'pending':
                total_pending += 1
            elif status == 'paid':
                total_paid += 1
            elif status == 'shipped':
                total_shipped += 1
            elif status == 'delivered':
                total_delivered += 1
            elif status == 'cancelled':
                total_cancelled += 1
            
            if claim.get('shipping_fee_paid') == 'true':
                payment_paid += 1
                total_revenue += 120.00
            else:
                payment_unpaid += 1
            
            size = claim.get('clothing_size', '')
            if size in size_distribution:
                size_distribution[size] += 1
            
            country = claim.get('country', 'Unknown')
            country_distribution[country] = country_distribution.get(country, 0) + 1
        
        recent_claims = claims[:10] if claims else []
        
        payments_result = supabase_select('payments')
        if payments_result and isinstance(payments_result, list):
            payment_revenue = 0.0
            for payment in payments_result:
                payment_revenue += float(payment.get('amount', 0))
            total_revenue = max(total_revenue, payment_revenue)
        
        codes_result = supabase_select('claim_codes')
        total_codes = 0
        used_codes = 0
        active_codes = 0
        
        if codes_result and isinstance(codes_result, list):
            total_codes = len(codes_result)
            for code in codes_result:
                if code.get('status') == 'active':
                    active_codes += 1
                elif code.get('status') == 'used':
                    used_codes += 1
        
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        today_claims = [c for c in claims if c.get('claim_date', '').startswith(today)]
        today_count = len(today_claims)
        
        this_month = datetime.datetime.now().strftime('%Y-%m')
        this_month_claims = [c for c in claims if c.get('claim_date', '').startswith(this_month)]
        this_month_count = len(this_month_claims)
        
        conversion_rate = 0
        if total_claims > 0:
            conversion_rate = round((payment_paid / total_claims) * 100, 1)
        
        return render_template('admin/dashboard.html',
                             company_name=COMPANY_NAME,
                             total_claims=total_claims,
                             total_paid=total_paid,
                             total_pending=total_pending,
                             total_shipped=total_shipped,
                             total_delivered=total_delivered,
                             total_cancelled=total_cancelled,
                             total_revenue=total_revenue,
                             payment_paid=payment_paid,
                             payment_unpaid=payment_unpaid,
                             today_count=today_count,
                             this_month_count=this_month_count,
                             conversion_rate=conversion_rate,
                             recent_claims=recent_claims,
                             size_distribution=size_distribution,
                             country_distribution=country_distribution,
                             total_codes=total_codes,
                             used_codes=used_codes,
                             active_codes=active_codes,
                             current_year=datetime.datetime.now().year)
        
    except Exception as e:
        app.logger.error(f"Admin dashboard error: {str(e)}", exc_info=True)
        flash('Error loading dashboard data', 'error')
        return render_template('admin/dashboard.html',
                             company_name=COMPANY_NAME,
                             total_claims=0,
                             total_paid=0,
                             total_pending=0,
                             total_shipped=0,
                             total_delivered=0,
                             total_cancelled=0,
                             total_revenue=0,
                             payment_paid=0,
                             payment_unpaid=0,
                             today_count=0,
                             this_month_count=0,
                             conversion_rate=0,
                             recent_claims=[],
                             size_distribution={},
                             country_distribution={},
                             total_codes=0,
                             used_codes=0,
                             active_codes=0,
                             current_year=datetime.datetime.now().year)

@app.route('/admin/claims')
@admin_required
def admin_claims():
    try:
        status = request.args.get('status', '')
        search = request.args.get('search', '')
        
        claims_result = supabase_select('gift_claims', order_by='updated_at.desc')
        
        if claims_result and isinstance(claims_result, list):
            claims = claims_result
        else:
            claims = []
        
        if status:
            claims = [c for c in claims if c.get('status') == status]
        if search:
            search_lower = search.lower()
            claims = [c for c in claims if 
                     search_lower in c.get('full_name', '').lower() or 
                     search_lower in c.get('email', '').lower() or
                     search_lower in c.get('claim_number', '').lower() or
                     search_lower in c.get('channel_name', '').lower()]
        
        status_counts = {
            'all': len(claims),
            'pending': len([c for c in claims if c.get('status') == 'pending']),
            'paid': len([c for c in claims if c.get('status') == 'paid']),
            'shipped': len([c for c in claims if c.get('status') == 'shipped']),
            'delivered': len([c for c in claims if c.get('status') == 'delivered']),
            'cancelled': len([c for c in claims if c.get('status') == 'cancelled'])
        }
        
        return render_template('admin/claims.html',
                             company_name=COMPANY_NAME,
                             claims=claims,
                             status_counts=status_counts,
                             current_status=status,
                             current_year=datetime.datetime.now().year)
                             
    except Exception as e:
        app.logger.error(f"Admin claims error: {str(e)}")
        flash('Error loading claims', 'error')
        return render_template('admin/claims.html',
                             company_name=COMPANY_NAME,
                             claims=[],
                             status_counts={},
                             current_status='',
                             current_year=datetime.datetime.now().year)

@app.route('/admin/claim/<claim_id>')
@admin_required
def admin_claim_detail(claim_id):
    try:
        result = supabase_select('gift_claims', {'id': claim_id})
        
        if not result or (isinstance(result, dict) and 'error' in result):
            flash('Claim not found', 'error')
            return redirect(url_for('admin_claims'))
        
        claim = result[0] if isinstance(result, list) else result
        
        payment = None
        try:
            payment_result = supabase_select('payments', {'claim_id': claim_id})
            if payment_result and isinstance(payment_result, list) and len(payment_result) > 0:
                payment = payment_result[0]
        except Exception as e:
            app.logger.error(f"Error fetching payment: {str(e)}")
        
        return render_template('admin/claim_detail.html',
                             company_name=COMPANY_NAME,
                             claim=claim,
                             payment=payment,
                             current_year=datetime.datetime.now().year)
                             
    except Exception as e:
        app.logger.error(f"Admin claim detail error: {str(e)}")
        flash('Error loading claim details', 'error')
        return redirect(url_for('admin_claims'))

@app.route('/admin/claim/update/<claim_id>', methods=['POST'])
@admin_required
def admin_update_claim(claim_id):
    try:
        action = request.form.get('action')
        tracking_number = request.form.get('tracking_number', '')
        
        update_data = {}
        
        if action == 'mark_shipped':
            update_data['status'] = 'shipped'
            update_data['tracking_number'] = tracking_number
            update_data['shipped_date'] = datetime.datetime.now().isoformat()
            flash('Claim marked as shipped', 'success')
        elif action == 'mark_delivered':
            update_data['status'] = 'delivered'
            update_data['delivered_date'] = datetime.datetime.now().isoformat()
            flash('Claim marked as delivered', 'success')
        elif action == 'mark_paid':
            update_data['status'] = 'paid'
            update_data['shipping_fee_paid'] = 'true'
            update_data['payment_status'] = 'success'
            flash('Claim marked as paid', 'success')
        elif action == 'mark_cancelled':
            update_data['status'] = 'cancelled'
            flash('Claim cancelled', 'warning')
        
        if update_data:
            update_data['updated_at'] = datetime.datetime.now().isoformat()
            supabase_update('gift_claims', update_data, {'id': claim_id})
        
        return redirect(url_for('admin_claim_detail', claim_id=claim_id))
    except Exception as e:
        app.logger.error(f"Admin update claim error: {str(e)}")
        flash('Error updating claim', 'error')
        return redirect(url_for('admin_claim_detail', claim_id=claim_id))

@app.route('/admin/codes')
@admin_required
def admin_codes():
    try:
        codes_result = supabase_select('claim_codes', order_by='created_at.desc')
        
        if codes_result and isinstance(codes_result, list):
            codes = codes_result
        else:
            codes = []
        
        for code in codes:
            if code.get('used_by_claim_id'):
                claim_result = supabase_select('gift_claims', {'id': code.get('used_by_claim_id')})
                if claim_result and isinstance(claim_result, list) and len(claim_result) > 0:
                    code['used_by_claim'] = claim_result[0]
        
        total_codes = len(codes)
        active_codes = len([c for c in codes if c.get('status') == 'active'])
        used_codes = len([c for c in codes if c.get('status') == 'used'])
        expired_codes = len([c for c in codes if c.get('status') == 'expired'])
        
        return render_template('admin/codes.html',
                             company_name=COMPANY_NAME,
                             codes=codes,
                             total_codes=total_codes,
                             active_codes=active_codes,
                             used_codes=used_codes,
                             expired_codes=expired_codes,
                             current_year=datetime.datetime.now().year)
                             
    except Exception as e:
        app.logger.error(f"Admin codes error: {str(e)}")
        flash('Error loading codes', 'error')
        return render_template('admin/codes.html',
                             company_name=COMPANY_NAME,
                             codes=[],
                             total_codes=0,
                             active_codes=0,
                             used_codes=0,
                             expired_codes=0,
                             current_year=datetime.datetime.now().year)

@app.route('/admin/codes/generate', methods=['POST'])
@admin_required
def admin_generate_codes():
    try:
        count = int(request.form.get('count', 10))
        if count > 100:
            count = 100
            flash('Maximum 100 codes at a time', 'warning')
        elif count < 1:
            count = 1
        
        description = request.form.get('description', '')
        expires_days = int(request.form.get('expires_days', 0))
        
        codes = generate_bulk_codes(count)
        
        inserted = 0
        failed = 0
        
        for code_data in codes:
            if description:
                code_data['description'] = description
            if expires_days > 0:
                code_data['expires_at'] = (datetime.datetime.now() + datetime.timedelta(days=expires_days)).isoformat()
            
            result = supabase_insert('claim_codes', code_data)
            
            if isinstance(result, dict) and 'error' in result:
                failed += 1
            else:
                inserted += 1
        
        if inserted > 0:
            flash(f'✅ {inserted} claim codes generated successfully!', 'success')
        if failed > 0:
            flash(f'⚠️ {failed} codes failed to generate', 'warning')
        
        return redirect(url_for('admin_codes'))
        
    except Exception as e:
        app.logger.error(f"Generate codes error: {str(e)}", exc_info=True)
        flash(f'Error generating codes: {str(e)}', 'error')
        return redirect(url_for('admin_codes'))

@app.route('/admin/codes/delete/<code_id>', methods=['POST'])
@admin_required
def admin_delete_code(code_id):
    try:
        result = supabase_select('claim_codes', {'id': code_id})
        if result and isinstance(result, list) and len(result) > 0:
            code = result[0]
            if code.get('status') == 'used':
                flash('Cannot delete a used code', 'error')
                return redirect(url_for('admin_codes'))
        
        url = f"{SUPABASE_URL}/rest/v1/claim_codes?id=eq.{code_id}"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        response = requests.delete(url, headers=headers, timeout=30)
        
        if response.status_code in [200, 204]:
            flash('Code deleted successfully', 'success')
        else:
            flash('Error deleting code', 'error')
        
        return redirect(url_for('admin_codes'))
        
    except Exception as e:
        app.logger.error(f"Delete code error: {str(e)}")
        flash('Error deleting code', 'error')
        return redirect(url_for('admin_codes'))

@app.route('/admin/codes/bulk-delete', methods=['POST'])
@admin_required
def admin_bulk_delete_codes():
    try:
        code_ids = request.form.getlist('code_ids')
        
        if not code_ids:
            flash('No codes selected for deletion', 'warning')
            return redirect(url_for('admin_codes'))
        
        deleted_count = 0
        failed_count = 0
        
        for code_id in code_ids:
            result = supabase_select('claim_codes', {'id': code_id})
            if result and isinstance(result, list) and len(result) > 0:
                code = result[0]
                if code.get('status') == 'used':
                    failed_count += 1
                    continue
                
                url = f"{SUPABASE_URL}/rest/v1/claim_codes?id=eq.{code_id}"
                headers = {
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json"
                }
                response = requests.delete(url, headers=headers, timeout=30)
                
                if response.status_code in [200, 204]:
                    deleted_count += 1
                else:
                    failed_count += 1
        
        if deleted_count > 0:
            flash(f'✅ {deleted_count} code(s) deleted successfully', 'success')
        if failed_count > 0:
            flash(f'⚠️ {failed_count} code(s) could not be deleted (they may be in use)', 'warning')
        
        return redirect(url_for('admin_codes'))
        
    except Exception as e:
        app.logger.error(f"Bulk delete codes error: {str(e)}")
        flash('Error deleting codes', 'error')
        return redirect(url_for('admin_codes'))

@app.route('/admin/export')
@admin_required
def admin_export():
    try:
        claims_result = supabase_select('gift_claims', order_by='updated_at.desc')
        
        if not claims_result or isinstance(claims_result, dict):
            flash('No claims to export', 'warning')
            return redirect(url_for('admin_claims'))
        
        claims = claims_result if isinstance(claims_result, list) else []
        
        si = StringIO()
        cw = csv.writer(si)
        
        cw.writerow([
            'Claim Number', 'Name', 'Email', 'Channel Name', 'Channel URL',
            'Phone', 'Country', 'Address', 'City', 'Postal Code',
            'Clothing Size', 'Status', 'Shipping Fee Paid', 'Payment Status', 'Created At'
        ])
        
        for claim in claims:
            cw.writerow([
                claim.get('claim_number', ''),
                claim.get('full_name', ''),
                claim.get('email', ''),
                claim.get('channel_name', ''),
                claim.get('channel_url', ''),
                claim.get('phone', ''),
                claim.get('country', ''),
                claim.get('address', ''),
                claim.get('city', ''),
                claim.get('postal_code', ''),
                claim.get('clothing_size', ''),
                claim.get('status', ''),
                claim.get('shipping_fee_paid', ''),
                claim.get('payment_status', ''),
                claim.get('created_at', '') or claim.get('claim_date', '')
            ])
        
        output = si.getvalue()
        
        return Response(
            output,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=gift_claims_{datetime.datetime.now().strftime("%Y%m%d")}.csv'
            }
        )
    except Exception as e:
        app.logger.error(f"Export error: {str(e)}")
        flash('Error exporting claims', 'error')
        return redirect(url_for('admin_claims'))

@app.route('/admin/export-codes')
@admin_required
def admin_export_codes():
    try:
        codes_result = supabase_select('claim_codes', order_by='created_at.desc')
        
        if not codes_result or isinstance(codes_result, dict):
            flash('No codes to export', 'warning')
            return redirect(url_for('admin_codes'))
        
        codes = codes_result if isinstance(codes_result, list) else []
        
        si = StringIO()
        cw = csv.writer(si)
        
        cw.writerow(['Code', 'Status', 'Description', 'Created At', 'Used At', 'Used By'])
        
        for code in codes:
            used_by = ''
            if code.get('used_by_claim_id'):
                claim_result = supabase_select('gift_claims', {'id': code.get('used_by_claim_id')})
                if claim_result and isinstance(claim_result, list) and len(claim_result) > 0:
                    used_by = claim_result[0].get('claim_number', '')
            
            cw.writerow([
                code.get('code', ''),
                code.get('status', ''),
                code.get('description', ''),
                code.get('created_at', '')[:10] if code.get('created_at') else '',
                code.get('used_at', '')[:10] if code.get('used_at') else '',
                used_by
            ])
        
        output = si.getvalue()
        
        return Response(
            output,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=claim_codes_{datetime.datetime.now().strftime("%Y%m%d")}.csv'
            }
        )
        
    except Exception as e:
        app.logger.error(f"Export codes error: {str(e)}")
        flash('Error exporting codes', 'error')
        return redirect(url_for('admin_codes'))

# ============================================================
# ERROR HANDLERS
# ============================================================
@app.errorhandler(404)
def not_found(e):
    return render_template('landing.html', company_name=COMPANY_NAME), 404

@app.errorhandler(500)
def internal_error(e):
    app.logger.error(f"500 error: {str(e)}")
    return render_template('error.html', company_name=COMPANY_NAME), 500

# ============================================================
# CONTEXT PROCESSOR
# ============================================================
@app.context_processor
def inject_globals():
    return {
        'company_name': COMPANY_NAME,
        'company_email': COMPANY_EMAIL,
        'campaign_name': CAMPAIGN_NAME,
        'reward_name': REWARD_NAME,
        'current_year': datetime.datetime.now().year
    }

# ============================================================
# RUN APP
# ============================================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV', 'production') != 'production'
    
    print("=" * 50)
    print(f"🎁 YouTube Creator Gift Box Campaign")
    print(f"📍 http://localhost:{port}")
    print(f"📊 Supabase: {'✅ Configured' if SUPABASE_URL and SUPABASE_KEY else '❌ Not Configured'}")
    print(f"💳 Paystack: {'✅ Configured' if PAYSTACK_SECRET else '❌ Not Configured'}")
    print(f"📧 Email: {'✅ Configured' if MAIL_USERNAME and MAIL_PASSWORD else '❌ Not Configured'}")
    print(f"🔐 Admin: http://localhost:{port}/admin/login (password: {ADMIN_PASSWORD})")
    print("=" * 50)
    print("\n⚠️ IMPORTANT DISCLAIMER:")
    print("   This campaign is NOT affiliated with, endorsed by, or sponsored by YouTube or Google.")
    print("=" * 50)
    
    app.run(debug=debug, host='0.0.0.0', port=port)