#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import io
import uuid
import datetime
import re
import hmac
import threading
import time
import base64
import csv
import random
import string
from io import StringIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, Response
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import requests
import logging
from logging.handlers import RotatingFileHandler

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

load_dotenv()

app = Flask(__name__)

# ============================================================
# SECRET KEY & SESSION
# ============================================================
app.secret_key = os.getenv('SECRET_KEY', 'change-me-in-render-env-vars')
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(minutes=30)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV', 'production') == 'production'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_REFRESH_EACH_REQUEST'] = True
app.config['SESSION_PERMANENT'] = True

# CSRF protection
csrf = CSRFProtect(app)

# Rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# ============================================================
# CONFIGURATION
# ============================================================
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

PAYSTACK_PUBLIC = os.getenv('PAYSTACK_PUBLIC_KEY')
PAYSTACK_SECRET = os.getenv('PAYSTACK_SECRET_KEY')
PAYSTACK_CALLBACK = os.getenv('PAYSTACK_CALLBACK_URL', 'https://creator-reward.onrender.com/payment/callback')

SHIPPING_FEE_USD = 120.00
USD_TO_NGN_RATE = 1500

# Gmail API Scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

COMPANY_NAME = os.getenv('COMPANY_NAME', 'Creator Rewards')
COMPANY_EMAIL = os.getenv('COMPANY_EMAIL', 'support@creatorrewards.com')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
CAMPAIGN_NAME = os.getenv('CAMPAIGN_NAME', 'YouTube Creator Gift Box 2026')
REWARD_NAME = os.getenv('REWARD_NAME', 'Creator Gift Package')

# Gmail API credentials
MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER')
GMAIL_API_CLIENT_ID = os.getenv('GMAIL_API_CLIENT_ID')
GMAIL_API_CLIENT_SECRET = os.getenv('GMAIL_API_CLIENT_SECRET')
GMAIL_API_REFRESH_TOKEN = os.getenv('GMAIL_API_REFRESH_TOKEN')

# Setup logging
if not os.path.exists('logs'):
    os.mkdir('logs')
file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

app.logger.info("=" * 60)
app.logger.info("GMAIL API CREDENTIALS CHECK")
app.logger.info(f"CLIENT_ID set: {bool(GMAIL_API_CLIENT_ID)}")
app.logger.info(f"CLIENT_SECRET set: {bool(GMAIL_API_CLIENT_SECRET)}")
app.logger.info(f"REFRESH_TOKEN set: {bool(GMAIL_API_REFRESH_TOKEN)}")
app.logger.info("=" * 60)

# ============================================================
# SAFE LOG MESSAGE
# ============================================================
def safe_log_message(msg):
    emoji_pattern = re.compile("["
                               u"\U0001F600-\U0001F64F"
                               u"\U0001F300-\U0001F5FF"
                               u"\U0001F680-\U0001F6FF"
                               u"\U0001F1E0-\U0001F1FF"
                               u"\U00002702-\U000027B0"
                               u"\U000024C2-\U0001F251"
                               "]+", flags=re.UNICODE)
    return emoji_pattern.sub('', msg)

# ============================================================
# SUPABASE HELPERS
# ============================================================
def supabase_select(table, filters=None, order_by=None, limit=None):
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
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            return response.json()
        else:
            return {'error': f'HTTP {response.status_code}', 'detail': response.text}
    except Exception as e:
        return {'error': str(e)}

def supabase_insert(table, data):
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
        response = requests.post(url, headers=headers, json=data, timeout=15)
        if response.status_code in [200, 201]:
            return response.json()
        else:
            return {'error': f'HTTP {response.status_code}', 'detail': response.text}
    except Exception as e:
        return {'error': str(e)}

def supabase_update(table, data, filters):
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
        response = requests.patch(url, headers=headers, params=params, json=data, timeout=15)
        if response.status_code in [200, 201]:
            return response.json()
        else:
            return {'error': f'HTTP {response.status_code}', 'detail': response.text}
    except Exception as e:
        return {'error': str(e)}

def supabase_delete(table, record_id):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {'error': 'Supabase not configured'}

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    params = {"id": f"eq.{record_id}"}

    try:
        response = requests.delete(url, headers=headers, params=params, timeout=15)
        return response.status_code in [200, 204]
    except Exception as e:
        app.logger.error(f"Delete error: {str(e)}")
        return False

# ============================================================
# CLAIM CODE GENERATION
# ============================================================
def generate_unique_code():
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
    codes = []
    for _ in range(count):
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
# GMAIL API EMAIL SYSTEM
# ============================================================
def get_gmail_service():
    """Get authenticated Gmail API service."""
    try:
        if not GMAIL_API_CLIENT_ID or not GMAIL_API_CLIENT_SECRET or not GMAIL_API_REFRESH_TOKEN:
            app.logger.error("Missing Gmail API credentials")
            return None

        creds = Credentials(
            token=None,
            refresh_token=GMAIL_API_REFRESH_TOKEN,
            client_id=GMAIL_API_CLIENT_ID,
            client_secret=GMAIL_API_CLIENT_SECRET,
            token_uri='https://oauth2.googleapis.com/token',
            scopes=SCOPES
        )

        creds.refresh(Request())

        if creds.valid:
            return build('gmail', 'v1', credentials=creds)
        else:
            app.logger.error("Credentials not valid after refresh")
            return None

    except Exception as e:
        app.logger.error(f"Gmail API error: {str(e)}")
        return None

def send_email(recipient, subject, template_name, **kwargs):
    """Send email using Gmail API with retry logic"""
    max_retries = 3
    retry_delay = 2

    app.logger.info(f"Attempting to send email to: {recipient}")
    app.logger.info(f"Subject: {subject}")
    app.logger.info(f"Template: {template_name}")

    for attempt in range(max_retries):
        try:
            service = get_gmail_service()
            if not service:
                app.logger.error(f"No Gmail service (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return False

            with app.app_context():
                html_content = render_template(f'emails/{template_name}.html', **kwargs)
                app.logger.info(f"HTML rendered: {len(html_content)} characters")

            message = MIMEMultipart('alternative')
            message['to'] = recipient
            message['subject'] = subject
            message['from'] = MAIL_DEFAULT_SENDER
            message['reply-to'] = COMPANY_EMAIL

            message['X-Mailer'] = 'Creator Rewards Platform'
            message['X-Priority'] = '3'
            message['List-Unsubscribe'] = f'<mailto:{COMPANY_EMAIL}?subject=Unsubscribe>'

            claim = kwargs.get('claim', {})
            plain_text = f"""
{subject}

Claim Number: {claim.get('claim_number', 'N/A')}
Name: {claim.get('full_name', 'N/A')}
Email: {claim.get('email', 'N/A')}

This is an automated message from {COMPANY_NAME}.

If you did not request this email, please ignore it.

For support: {COMPANY_EMAIL}

---
{COMPANY_NAME}
Not affiliated with YouTube or Google
            """
            text_part = MIMEText(plain_text, 'plain')
            html_part = MIMEText(html_content, 'html')
            message.attach(text_part)
            message.attach(html_part)

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

            app.logger.info(f"Sending via Gmail API...")
            service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()

            app.logger.info(f"Email sent successfully to {recipient} from {MAIL_DEFAULT_SENDER}")
            return True

        except Exception as e:
            app.logger.error(f"Email error (attempt {attempt + 1}): {str(e)}")
            if attempt < max_retries - 1:
                app.logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                continue

    app.logger.error(f"Failed to send email after {max_retries} attempts")
    return False

# ============================================================
# EMAIL TEMPLATE FUNCTIONS
# ============================================================
def send_claim_confirmation(claim_data):
    payment_url = f"https://creator-reward.onrender.com/payment/{claim_data['id']}"

    app.logger.info(f"Sending confirmation email to user: {claim_data['email']}")

    result = send_email(
        recipient=claim_data['email'],
        subject=f"Claim Received - {claim_data['claim_number']}",
        template_name='claim_confirmation',
        claim=claim_data,
        payment_url=payment_url,
        company_name=COMPANY_NAME,
        company_email=COMPANY_EMAIL,
        campaign_name=CAMPAIGN_NAME,
        reward_name=REWARD_NAME,
        shipping_fee=SHIPPING_FEE_USD,
        current_year=datetime.datetime.now().year
    )

    if result:
        app.logger.info(f"Confirmation email sent to {claim_data['email']}")
    else:
        app.logger.error(f"Failed to send confirmation email to {claim_data['email']}")

    return result

def send_admin_notification(claim_data):
    app.logger.info(f"Sending admin notification to: {ADMIN_EMAIL}")

    result = send_email(
        recipient=ADMIN_EMAIL,
        subject=f"New Claim Submitted - {claim_data['claim_number']}",
        template_name='admin_notification',
        claim=claim_data,
        company_name=COMPANY_NAME,
        company_email=COMPANY_EMAIL,
        reward_name=REWARD_NAME,
        current_year=datetime.datetime.now().year
    )

    if result:
        app.logger.info(f"Admin notification sent for claim {claim_data['claim_number']}")
    else:
        app.logger.error(f"Failed to send admin notification for claim {claim_data['claim_number']}")

    return result

def send_payment_receipt(claim_data, payment_data):
    result = send_email(
        recipient=claim_data['email'],
        subject=f"Payment Confirmed - {claim_data['claim_number']}",
        template_name='payment_receipt',
        claim=claim_data,
        payment=payment_data,
        company_name=COMPANY_NAME,
        company_email=COMPANY_EMAIL,
        reward_name=REWARD_NAME,
        current_year=datetime.datetime.now().year
    )
    if result:
        app.logger.info(f"Payment receipt sent to {claim_data['email']}")
    else:
        app.logger.error(f"Failed to send payment receipt to {claim_data['email']}")
    return result

def send_payment_failed(claim_data, error_message=None):
    payment_url = f"https://creator-reward.onrender.com/payment/{claim_data['id']}"
    result = send_email(
        recipient=claim_data['email'],
        subject=f"Payment Failed - {claim_data['claim_number']}",
        template_name='payment_failed',
        claim=claim_data,
        payment_url=payment_url,
        error_message=error_message,
        company_name=COMPANY_NAME,
        company_email=COMPANY_EMAIL,
        reward_name=REWARD_NAME,
        current_year=datetime.datetime.now().year
    )
    if result:
        app.logger.info(f"Payment failed email sent to {claim_data['email']}")
    else:
        app.logger.error(f"Failed to send payment failed email to {claim_data['email']}")
    return result

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

def check_admin_password(candidate):
    if not ADMIN_PASSWORD or not candidate:
        return False
    return hmac.compare_digest(candidate, ADMIN_PASSWORD)

# ============================================================
# UTILITY FUNCTIONS
# ============================================================
def generate_claim_number():
    year = datetime.datetime.now().year
    try:
        result = supabase_select('gift_claims', order_by='updated_at.desc', limit=1)
        if result and isinstance(result, list) and len(result) > 0:
            last_num = int(result[0]['claim_number'].split('-')[-1])
            new_num = last_num + 1
            claim_number = f"GC-{year}-{new_num:04d}"
            check = supabase_select('gift_claims', filters={'claim_number': claim_number})
            if check and isinstance(check, list) and len(check) == 0:
                return claim_number
    except Exception as e:
        app.logger.error(f"generate_claim_number error: {str(e)}")
    return f"GC-{year}-{random.randint(1000, 9999):04d}"

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
    # Clear flash messages on landing page to prevent admin messages showing
    session.pop('_flashes', None)
    return render_template('landing.html',
                         company_name=COMPANY_NAME,
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

@app.route('/claim', methods=['GET', 'POST'])
@limiter.limit("10 per hour", methods=['POST'])
def claim_form():
    if request.method == 'GET':
        # Clear flash messages when accessing claim page
        session.pop('_flashes', None)
        return render_template('claim_form.html',
                             company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME,
                             reward_name=REWARD_NAME)

    data = request.form
    app.logger.info(f"Form data received for claim from {request.remote_addr}")

    required = ['full_name', 'email', 'channel_name', 'phone', 'country', 'address', 'city', 'postal_code', 'clothing_size', 'claim_code']
    for field in required:
        if not data.get(field, '').strip():
            flash(f'Please fill in {field.replace("_", " ")}', 'error')
            return render_template('claim_form.html', company_name=COMPANY_NAME,
                                 campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

    if not validate_email(data['email']):
        flash('Please enter a valid email address', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

    if not validate_phone(data['phone']):
        flash('Please enter a valid phone number', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

    code_result = supabase_select('claim_codes', {'code': data['claim_code'].upper()})
    if not code_result or (isinstance(code_result, dict) and 'error' in code_result) or len(code_result) == 0:
        flash('Invalid claim code. Please check your code and try again.', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

    code_data = code_result[0]
    if code_data.get('status') != 'active':
        flash('This claim code has already been used or expired.', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

    claim_code_id = code_data['id']
    claim_number = generate_claim_number()

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
        result = supabase_insert('gift_claims', claim_data)
        if isinstance(result, dict) and 'error' in result:
            flash('Database error. Please try again.', 'error')
            return render_template('claim_form.html', company_name=COMPANY_NAME,
                                 campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

        claim_id = result[0]['id'] if result and isinstance(result, list) and len(result) > 0 else str(uuid.uuid4())
        claim_data['id'] = claim_id

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
                    app.logger.info(f"Starting background email sending for claim {claim_number}")

                    app.logger.info(f"Sending confirmation to user: {claim_data['email']}")
                    confirmation_sent = send_claim_confirmation(claim_data)
                    if confirmation_sent:
                        app.logger.info(f"User confirmation sent")
                    else:
                        app.logger.error(f"User confirmation FAILED")

                    app.logger.info(f"Sending admin notification to: {ADMIN_EMAIL}")
                    admin_sent = send_admin_notification(claim_data)
                    if admin_sent:
                        app.logger.info(f"Admin notification sent")
                    else:
                        app.logger.error(f"Admin notification FAILED")

                    if confirmation_sent and admin_sent:
                        app.logger.info(f"All emails sent for claim {claim_number}")
                    else:
                        app.logger.warning(f"Partial email success for claim {claim_number}: user={confirmation_sent}, admin={admin_sent}")

                except Exception as e:
                    app.logger.error(f"Background email error: {str(e)}")
                    import traceback
                    app.logger.error(traceback.format_exc())

        email_thread = threading.Thread(target=send_emails_in_background, daemon=True)
        email_thread.start()
        app.logger.info(f"Background email thread started for claim {claim_number}")

        flash('Your gift claim has been submitted successfully!', 'success')
        return redirect(url_for('review_claim', claim_id=claim_id))

    except Exception as e:
        app.logger.error(f"Exception in claim submission: {str(e)}", exc_info=True)
        flash('An error occurred. Please try again.', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

@app.route('/review/<claim_id>')
def review_claim(claim_id):
    result = supabase_select('gift_claims', {'id': claim_id})
    if not result or (isinstance(result, dict) and 'error' in result):
        flash('Claim not found.', 'error')
        return redirect(url_for('claim_form'))

    claim = result[0] if isinstance(result, list) else result
    return render_template('review.html',
                         claim=claim,
                         shipping_fee=SHIPPING_FEE_USD,
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
            flash('Payment system not configured.', 'error')
            return redirect(url_for('review_claim', claim_id=claim_id))

        payment_ref = generate_payment_reference()
        supabase_update('gift_claims', {
            'payment_reference': payment_ref,
            'status': 'payment_pending',
            'updated_at': datetime.datetime.now().isoformat()
        }, {'id': claim_id})

        amount_in_kobo = int(SHIPPING_FEE_USD * USD_TO_NGN_RATE * 100)
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
                'usd_amount': SHIPPING_FEE_USD,
                'exchange_rate': USD_TO_NGN_RATE
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
            if claim_id_from_metadata:
                result = supabase_select('gift_claims', {'id': claim_id_from_metadata})
                if result and isinstance(result, list) and len(result) > 0:
                    claim = result[0]

            if not claim:
                result = supabase_select('gift_claims', {'payment_reference': reference})
                if result and isinstance(result, list) and len(result) > 0:
                    claim = result[0]

            if claim:
                claim_id = claim['id']

                if claim.get('shipping_fee_paid') == 'true':
                    flash('Payment already processed.', 'info')
                    return redirect(url_for('confirmation', claim_id=claim_id))

                expected_kobo = int(SHIPPING_FEE_USD * USD_TO_NGN_RATE * 100)
                paid_kobo = data['data'].get('amount', 0)
                if paid_kobo != expected_kobo:
                    app.logger.error(
                        f"Amount mismatch for claim {claim_id}: "
                        f"expected {expected_kobo}, got {paid_kobo}"
                    )
                    flash('Payment amount mismatch. Please contact support.', 'error')
                    return redirect(url_for('landing'))

                claim_update_result = supabase_update('gift_claims', {
                    'status': 'paid',
                    'shipping_fee_paid': 'true',
                    'updated_at': datetime.datetime.now().isoformat()
                }, {'id': claim_id, 'shipping_fee_paid': 'false'})

                update_failed = isinstance(claim_update_result, dict) and 'error' in claim_update_result
                already_claimed_by_other_request = (
                    not update_failed
                    and isinstance(claim_update_result, list)
                    and len(claim_update_result) == 0
                )

                if update_failed:
                    app.logger.error(f"Failed to mark claim {claim_id} as paid: {claim_update_result}")
                    flash('Payment verification error. Please contact support.', 'error')
                    return redirect(url_for('landing'))

                if already_claimed_by_other_request:
                    app.logger.info(
                        f"Duplicate payment callback for claim {claim_id} "
                        f"(reference {reference}) - already processed by another request, skipping."
                    )
                    flash('Payment already processed.', 'info')
                    return redirect(url_for('confirmation', claim_id=claim_id))

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
                        except Exception as e:
                            app.logger.error(f"Receipt email error: {str(e)}")

                threading.Thread(target=send_receipt_in_background, daemon=True).start()

                flash('Payment successful! Your gift package is being prepared.', 'success')
                return redirect(url_for('confirmation', claim_id=claim_id))
            else:
                flash('Claim not found for this payment.', 'error')
                return redirect(url_for('landing'))
        else:
            claim = None
            result = supabase_select('gift_claims', {'payment_reference': reference})
            if result and isinstance(result, list) and len(result) > 0:
                claim = result[0]
                error_message = data.get('message', 'Payment verification failed')

                def send_failed_in_background():
                    with app.app_context():
                        try:
                            send_payment_failed(claim, error_message)
                        except Exception as e:
                            app.logger.error(f"Payment failed email error: {str(e)}")

                threading.Thread(target=send_failed_in_background, daemon=True).start()

            flash('Payment verification failed. Please try again.', 'error')
            return redirect(url_for('landing'))

    except Exception as e:
        app.logger.error(f"Callback error: {str(e)}")
        flash('Payment verification error. Please contact support.', 'error')
        return redirect(url_for('landing'))

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

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'supabase_configured': bool(SUPABASE_URL and SUPABASE_KEY),
        'paystack_configured': bool(PAYSTACK_SECRET),
        'gmail_api_configured': bool(GMAIL_API_CLIENT_ID and GMAIL_API_REFRESH_TOKEN),
        'timestamp': datetime.datetime.now().isoformat()
    })

@app.route('/clear-flash', methods=['POST'])
def clear_flash():
    """Clear flash messages from session"""
    session.pop('_flakes', None)
    return jsonify({'status': 'cleared'})

# ============================================================
# ROUTES - ADMIN
# ============================================================
@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit("10 per hour", methods=['POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        if check_admin_password(password):
            session.clear()
            session['admin_logged_in'] = True
            session['admin_user'] = 'Administrator'
            session.permanent = True
            flash('Welcome Admin!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid password', 'error')

    return render_template('admin/login.html', company_name=COMPANY_NAME)

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    try:
        claims_result = supabase_select('gift_claims', order_by='updated_at.desc', limit=50)

        if isinstance(claims_result, dict) and 'error' in claims_result:
            app.logger.error(f"Supabase error: {claims_result.get('detail', 'Unknown error')}")
            claims = []
        else:
            claims = claims_result if isinstance(claims_result, list) else []

        total_claims = len(claims)
        total_paid = 0
        total_pending = 0
        total_revenue = 0.0

        for claim in claims:
            if claim.get('shipping_fee_paid') == 'true':
                total_paid += 1
                total_revenue += SHIPPING_FEE_USD
            if claim.get('status') == 'pending':
                total_pending += 1

        return render_template('admin/dashboard.html',
                             company_name=COMPANY_NAME,
                             total_claims=total_claims,
                             total_paid=total_paid,
                             total_pending=total_pending,
                             total_revenue=total_revenue,
                             recent_claims=claims[:10],
                             current_year=datetime.datetime.now().year)
    except Exception as e:
        app.logger.error(f"Dashboard error: {str(e)}")
        flash('Error loading dashboard', 'error')
        return render_template('admin/dashboard.html', company_name=COMPANY_NAME,
                             total_claims=0, total_paid=0, total_pending=0, total_revenue=0,
                             recent_claims=[], current_year=datetime.datetime.now().year)

@app.route('/admin/claims')
@admin_required
def admin_claims():
    try:
        status = request.args.get('status', '')
        search = request.args.get('search', '')

        claims_result = supabase_select('gift_claims', order_by='updated_at.desc', limit=200)
        claims = claims_result if isinstance(claims_result, list) else []

        if status:
            claims = [c for c in claims if c.get('status') == status]
        if search:
            search_lower = search.lower()
            claims = [c for c in claims if
                     search_lower in c.get('full_name', '').lower() or
                     search_lower in c.get('email', '').lower() or
                     search_lower in c.get('claim_number', '').lower()]

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
                             claims=claims[:100],
                             status_counts=status_counts,
                             current_status=status,
                             current_year=datetime.datetime.now().year)
    except Exception as e:
        app.logger.error(f"Claims error: {str(e)}")
        flash('Error loading claims', 'error')
        return render_template('admin/claims.html', company_name=COMPANY_NAME,
                             claims=[], status_counts={}, current_status='', current_year=datetime.datetime.now().year)

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
        payment_result = supabase_select('payments', {'claim_id': claim_id})
        if payment_result and isinstance(payment_result, list) and len(payment_result) > 0:
            payment = payment_result[0]

        return render_template('admin/claim_detail.html',
                             company_name=COMPANY_NAME,
                             claim=claim,
                             payment=payment,
                             current_year=datetime.datetime.now().year)
    except Exception as e:
        app.logger.error(f"Claim detail error: {str(e)}")
        flash('Error loading claim details', 'error')
        return redirect(url_for('admin_claims'))

@app.route('/admin/claim/update/<claim_id>', methods=['POST'])
@admin_required
def admin_update_claim(claim_id):
    try:
        action = request.form.get('action')
        tracking_number = request.form.get('tracking_number', '')

        update_data = {'updated_at': datetime.datetime.now().isoformat()}
        if action == 'mark_shipped':
            update_data['status'] = 'shipped'
            update_data['tracking_number'] = tracking_number
            flash('Claim marked as shipped', 'success')
        elif action == 'mark_delivered':
            update_data['status'] = 'delivered'
            flash('Claim marked as delivered', 'success')
        elif action == 'mark_paid':
            update_data['status'] = 'paid'
            update_data['shipping_fee_paid'] = 'true'
            flash('Claim marked as paid', 'success')
        elif action == 'mark_cancelled':
            update_data['status'] = 'cancelled'
            flash('Claim cancelled', 'warning')

        supabase_update('gift_claims', update_data, {'id': claim_id})

        return redirect(url_for('admin_claim_detail', claim_id=claim_id))
    except Exception as e:
        app.logger.error(f"Update claim error: {str(e)}")
        flash('Error updating claim', 'error')
        return redirect(url_for('admin_claim_detail', claim_id=claim_id))

@app.route('/admin/export')
@admin_required
def admin_export():
    try:
        claims_result = supabase_select('gift_claims', order_by='updated_at.desc')
        claims = claims_result if isinstance(claims_result, list) else []

        si = StringIO()
        cw = csv.writer(si)
        cw.writerow(['Claim Number', 'Name', 'Email', 'Channel', 'Phone', 'Country', 'Address', 'City', 'Postal Code', 'Clothing Size', 'Status', 'Payment', 'Created At'])

        for claim in claims:
            cw.writerow([
                claim.get('claim_number', ''),
                claim.get('full_name', ''),
                claim.get('email', ''),
                claim.get('channel_name', ''),
                claim.get('phone', ''),
                claim.get('country', ''),
                claim.get('address', ''),
                claim.get('city', ''),
                claim.get('postal_code', ''),
                claim.get('clothing_size', ''),
                claim.get('status', ''),
                claim.get('shipping_fee_paid', ''),
                claim.get('claim_date', '')[:10] if claim.get('claim_date') else ''
            ])

        output = si.getvalue()
        return Response(output, mimetype='text/csv',
                       headers={'Content-Disposition': f'attachment; filename=gift_claims_{datetime.datetime.now().strftime("%Y%m%d")}.csv'})
    except Exception as e:
        app.logger.error(f"Export error: {str(e)}")
        flash('Error exporting claims', 'error')
        return redirect(url_for('admin_claims'))

@app.route('/admin/codes')
@admin_required
def admin_codes():
    try:
        codes_result = supabase_select('claim_codes', order_by='created_at.desc', limit=200)

        codes = codes_result if codes_result and isinstance(codes_result, list) else []

        for code in codes[:50]:
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
                             codes=codes[:100],
                             total_codes=total_codes,
                             active_codes=active_codes,
                             used_codes=used_codes,
                             expired_codes=expired_codes,
                             current_year=datetime.datetime.now().year)
    except Exception as e:
        app.logger.error(f"Codes error: {str(e)}")
        flash('Error loading codes', 'error')
        return render_template('admin/codes.html', company_name=COMPANY_NAME,
                             codes=[], total_codes=0, active_codes=0, used_codes=0, expired_codes=0,
                             current_year=datetime.datetime.now().year)

@app.route('/admin/codes/generate', methods=['POST'])
@admin_required
def admin_generate_codes():
    try:
        count = min(int(request.form.get('count', 10)), 100)
        description = request.form.get('description', '')
        expires_days = int(request.form.get('expires_days', 0))

        codes = generate_bulk_codes(count)
        inserted = 0

        for code_data in codes:
            if description:
                code_data['description'] = description
            if expires_days > 0:
                code_data['expires_at'] = (datetime.datetime.now() + datetime.timedelta(days=expires_days)).isoformat()

            result = supabase_insert('claim_codes', code_data)
            if not (isinstance(result, dict) and 'error' in result):
                inserted += 1

        flash(f'{inserted} claim codes generated successfully!', 'success')
        return redirect(url_for('admin_codes'))
    except Exception as e:
        app.logger.error(f"Generate codes error: {str(e)}")
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

            if supabase_delete('claim_codes', code_id):
                flash('Code deleted successfully', 'success')
            else:
                flash('Error deleting code', 'error')
        else:
            flash('Code not found', 'error')

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
        app.logger.info(f"Bulk delete requested for code_ids: {code_ids}")
        
        if not code_ids or len(code_ids) == 0:
            flash('No codes selected to delete.', 'warning')
            return redirect(url_for('admin_codes'))
        
        deleted = 0
        skipped = 0

        for code_id in code_ids:
            result = supabase_select('claim_codes', {'id': code_id})
            if result and isinstance(result, list) and len(result) > 0:
                code = result[0]
                if code.get('status') == 'used':
                    skipped += 1
                elif supabase_delete('claim_codes', code_id):
                    deleted += 1

        if deleted > 0 and skipped == 0:
            flash(f'{deleted} code(s) deleted successfully!', 'success')
        elif deleted > 0 and skipped > 0:
            flash(f'{deleted} code(s) deleted successfully. {skipped} code(s) skipped (already used).', 'warning')
        elif skipped > 0:
            flash(f'{skipped} code(s) were not deleted because they are already used.', 'warning')
        else:
            flash('No codes were deleted.', 'info')
            
        return redirect(url_for('admin_codes'))
    except Exception as e:
        app.logger.error(f"Bulk delete error: {str(e)}")
        flash('Error deleting codes. Please try again.', 'error')
        return redirect(url_for('admin_codes'))

@app.route('/admin/test-email')
@admin_required
def admin_test_email():
    try:
        result = send_email(
            recipient=ADMIN_EMAIL,
            subject=f"Test Email - {CAMPAIGN_NAME}",
            template_name='claim_confirmation',
            claim={
                'full_name': 'Test User',
                'claim_number': 'TEST-001',
                'email': ADMIN_EMAIL,
                'channel_name': 'Test Channel'
            },
            payment_url='https://creator-reward.onrender.com/payment/test',
            company_name=COMPANY_NAME,
            campaign_name=CAMPAIGN_NAME,
            reward_name=REWARD_NAME,
            current_year=datetime.datetime.now().year
        )

        if result:
            flash('Test email sent! Check your inbox.', 'success')
        else:
            flash('Email failed. Check logs.', 'error')

        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/check-session')
def admin_check_session():
    return jsonify({
        'logged_in': session.get('admin_logged_in', False),
        'session_keys': list(session.keys())
    })

# ============================================================
# RESEND EMAILS (Manual Trigger)
# ============================================================
@app.route('/admin/resend-emails/<claim_id>')
@admin_required
def admin_resend_emails(claim_id):
    try:
        result = supabase_select('gift_claims', {'id': claim_id})
        if not result or (isinstance(result, dict) and 'error' in result):
            flash('Claim not found', 'error')
            return redirect(url_for('admin_claims'))

        claim = result[0] if isinstance(result, list) else result

        confirmation_sent = send_claim_confirmation(claim)
        admin_sent = send_admin_notification(claim)

        if confirmation_sent and admin_sent:
            flash('Emails resent successfully!', 'success')
        elif confirmation_sent:
            flash('Confirmation email sent, but admin notification failed.', 'warning')
        elif admin_sent:
            flash('Admin notification sent, but confirmation email failed.', 'warning')
        else:
            flash('Both emails failed to send. Check logs.', 'error')

        return redirect(url_for('admin_claim_detail', claim_id=claim_id))

    except Exception as e:
        app.logger.error(f"Resend emails error: {str(e)}")
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('admin_claims'))

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
        'current_year': datetime.datetime.now().year,
        'is_admin_page': request.path.startswith('/admin/') if request else False
    }

# ============================================================
# RUN APP
# ============================================================
if __name__ == '__main__':
    print("=" * 50)
    print("YouTube Creator Gift Box Campaign")
    print("http://localhost:5000")
    print(f"Supabase: {'Configured' if SUPABASE_URL and SUPABASE_KEY else 'Not Configured'}")
    print(f"Paystack: {'Configured' if PAYSTACK_SECRET else 'Not Configured'}")
    print(f"Gmail API: {'Configured' if GMAIL_API_CLIENT_ID and GMAIL_API_REFRESH_TOKEN else 'Not Configured'}")
    print("=" * 50)
    app.run(debug=(os.getenv('FLASK_ENV') != 'production'), host='0.0.0.0', port=int(os.getenv('PORT', 5000)))