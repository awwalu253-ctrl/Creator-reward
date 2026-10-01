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
from werkzeug.security import generate_password_hash, check_password_hash
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
    max_retries = 3
    retry_delay = 2
    app.logger.info(f"Attempting to send email to: {recipient}")
    app.logger.info(f"Subject: {subject}")
    for attempt in range(max_retries):
        try:
            service = get_gmail_service()
            if not service:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return False
            with app.app_context():
                html_content = render_template(f'emails/{template_name}.html', **kwargs)
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

Registration Number: {claim.get('claim_number', 'N/A')}
Name: {claim.get('full_name', 'N/A')}
Email: {claim.get('email', 'N/A')}

This is an automated message from {COMPANY_NAME}.

For support: {COMPANY_EMAIL}
            """
            text_part = MIMEText(plain_text, 'plain')
            html_part = MIMEText(html_content, 'html')
            message.attach(text_part)
            message.attach(html_part)
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
            app.logger.info(f"Email sent to {recipient}")
            return True
        except Exception as e:
            app.logger.error(f"Email error (attempt {attempt + 1}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
    return False

# ============================================================
# EMAIL TEMPLATE FUNCTIONS
# ============================================================
def send_registration_confirmation(claim_data):
    """Send registration confirmation to the user"""
    app.logger.info(f"Sending registration confirmation to: {claim_data['email']}")
    result = send_email(
        recipient=claim_data['email'],
        subject=f"Congratulations - You're Registered! ({claim_data['claim_number']})",
        template_name='claim_confirmation',
        claim=claim_data,
        company_name=COMPANY_NAME,
        company_email=COMPANY_EMAIL,
        campaign_name=CAMPAIGN_NAME,
        reward_name=REWARD_NAME,
        current_year=datetime.datetime.now().year
    )
    if result:
        app.logger.info(f"Registration confirmation sent to {claim_data['email']}")
    else:
        app.logger.error(f"Failed to send registration confirmation to {claim_data['email']}")
    return result

def send_admin_notification(claim_data):
    """Send admin notification when new registration comes in"""
    app.logger.info(f"Sending admin notification to: {ADMIN_EMAIL}")
    result = send_email(
        recipient=ADMIN_EMAIL,
        subject=f"New Registration - {claim_data['claim_number']}",
        template_name='admin_notification',
        claim=claim_data,
        company_name=COMPANY_NAME,
        company_email=COMPANY_EMAIL,
        reward_name=REWARD_NAME,
        current_year=datetime.datetime.now().year
    )
    if result:
        app.logger.info(f"Admin notification sent")
    else:
        app.logger.error(f"Admin notification failed")
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
            claim_number = f"REG-{year}-{new_num:04d}"
            check = supabase_select('gift_claims', filters={'claim_number': claim_number})
            if check and isinstance(check, list) and len(check) == 0:
                return claim_number
    except Exception as e:
        app.logger.error(f"generate_claim_number error: {str(e)}")
    return f"REG-{year}-{random.randint(1000, 9999):04d}"

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    phone = re.sub(r'[^\d+]', '', phone)
    digits_only = re.sub(r'[^\d]', '', phone)
    return len(digits_only) >= 10

def validate_password(password):
    """Password must be at least 8 characters"""
    return len(password) >= 8

# ============================================================
# ROUTES - PUBLIC
# ============================================================
@app.route('/')
def landing():
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
        session.pop('_flashes', None)
        return render_template('claim_form.html',
                             company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME,
                             reward_name=REWARD_NAME)

    data = request.form
    app.logger.info(f"Registration form received from {request.remote_addr}")

    # Required fields
    required = ['full_name', 'email', 'password', 'address', 'postal_code', 'clothing_size']
    for field in required:
        if not data.get(field, '').strip():
            flash(f'Please fill in {field.replace("_", " ")}', 'error')
            return render_template('claim_form.html', company_name=COMPANY_NAME,
                                 campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

    if not validate_email(data['email']):
        flash('Please enter a valid email address', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

    if not validate_password(data['password']):
        flash('Password must be at least 8 characters', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

    # Phone
    phone_code = data.get('phone_code', '').strip()
    phone_number = data.get('phone_number', '').strip()
    if not phone_code or not phone_number:
        flash('Please enter your full phone number', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)
    full_phone = f"{phone_code}{phone_number}"
    if not validate_phone(full_phone):
        flash('Please enter a valid phone number', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

    # Country
    country = data.get('country', '').strip() or data.get('country_manual', '').strip()
    if not country:
        flash('Please select or enter your country', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

    # City
    city = data.get('city', '').strip() or data.get('city_manual', '').strip()
    if not city:
        flash('Please select or enter your city/state', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

    # Check for duplicate email
    existing = supabase_select('gift_claims', {'email': data['email'].strip().lower()})
    if existing and isinstance(existing, list) and len(existing) > 0:
        flash('This email is already registered.', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

    claim_number = generate_claim_number()

    # Hash the password before storing
    password_hash = generate_password_hash(data['password'])

    claim_data = {
        'claim_number': claim_number,
        'full_name': data['full_name'].strip(),
        'email': data['email'].strip().lower(),
        'password_hash': password_hash,
        'phone': full_phone,
        'country': country,
        'address': data['address'].strip(),
        'city': city,
        'postal_code': data['postal_code'].strip(),
        'clothing_size': data['clothing_size'].strip(),
        'claim_code': 'FREE-REGISTRATION',
        'status': 'registered',
        'shipping_fee_paid': 'n/a',
        'claim_date': datetime.datetime.now().isoformat(),
        'updated_at': datetime.datetime.now().isoformat()
    }

    app.logger.info(f"Inserting registration: {claim_data['email']}")

    try:
        result = supabase_insert('gift_claims', claim_data)
        if isinstance(result, dict) and 'error' in result:
            app.logger.error(f"Supabase error: {result}")
            flash('Registration failed. Please try again.', 'error')
            return render_template('claim_form.html', company_name=COMPANY_NAME,
                                 campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

        claim_id = result[0]['id'] if result and isinstance(result, list) and len(result) > 0 else str(uuid.uuid4())
        claim_data['id'] = claim_id

        session['claim_id'] = claim_id
        session['claim_number'] = claim_number

        # Send emails in background
        def send_emails_in_background():
            with app.app_context():
                try:
                    send_registration_confirmation(claim_data)
                    send_admin_notification(claim_data)
                except Exception as e:
                    app.logger.error(f"Background email error: {str(e)}")

        threading.Thread(target=send_emails_in_background, daemon=True).start()

        flash('Registration successful! Check your email for confirmation.', 'success')
        return redirect(url_for('confirmation', claim_id=claim_id))

    except Exception as e:
        app.logger.error(f"Exception in registration: {str(e)}", exc_info=True)
        flash('An error occurred. Please try again.', 'error')
        return render_template('claim_form.html', company_name=COMPANY_NAME,
                             campaign_name=CAMPAIGN_NAME, reward_name=REWARD_NAME, form_data=data)

@app.route('/confirmation/<claim_id>')
def confirmation(claim_id):
    result = supabase_select('gift_claims', {'id': claim_id})
    if not result or (isinstance(result, dict) and 'error' in result):
        flash('Registration not found.', 'error')
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
        'gmail_api_configured': bool(GMAIL_API_CLIENT_ID and GMAIL_API_REFRESH_TOKEN),
        'timestamp': datetime.datetime.now().isoformat()
    })

@app.route('/clear-flash', methods=['POST'])
def clear_flash():
    session.pop('_flashes', None)
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
            claims = []
        else:
            claims = claims_result if isinstance(claims_result, list) else []

        total_claims = len(claims)
        total_pending = len([c for c in claims if c.get('status') == 'registered'])
        total_contacted = len([c for c in claims if c.get('status') == 'contacted'])

        return render_template('admin/dashboard.html',
                             company_name=COMPANY_NAME,
                             total_claims=total_claims,
                             total_paid=total_contacted,
                             total_pending=total_pending,
                             total_revenue=0.0,
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
            'registered': len([c for c in claims if c.get('status') == 'registered']),
            'contacted': len([c for c in claims if c.get('status') == 'contacted']),
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
        flash('Error loading registrations', 'error')
        return render_template('admin/claims.html', company_name=COMPANY_NAME,
                             claims=[], status_counts={}, current_status='',
                             current_year=datetime.datetime.now().year)

@app.route('/admin/claim/<claim_id>')
@admin_required
def admin_claim_detail(claim_id):
    try:
        result = supabase_select('gift_claims', {'id': claim_id})
        if not result or (isinstance(result, dict) and 'error' in result):
            flash('Registration not found', 'error')
            return redirect(url_for('admin_claims'))

        claim = result[0] if isinstance(result, list) else result
        return render_template('admin/claim_detail.html',
                             company_name=COMPANY_NAME,
                             claim=claim,
                             current_year=datetime.datetime.now().year)
    except Exception as e:
        app.logger.error(f"Registration detail error: {str(e)}")
        flash('Error loading registration', 'error')
        return redirect(url_for('admin_claims'))

@app.route('/admin/claim/update/<claim_id>', methods=['POST'])
@admin_required
def admin_update_claim(claim_id):
    try:
        action = request.form.get('action')
        update_data = {'updated_at': datetime.datetime.now().isoformat()}

        if action == 'mark_contacted':
            update_data['status'] = 'contacted'
            flash('Registration marked as contacted', 'success')
        elif action == 'mark_cancelled':
            update_data['status'] = 'cancelled'
            flash('Registration cancelled', 'warning')

        if len(update_data) > 1:
            supabase_update('gift_claims', update_data, {'id': claim_id})

        return redirect(url_for('admin_claim_detail', claim_id=claim_id))
    except Exception as e:
        app.logger.error(f"Update registration error: {str(e)}")
        flash('Error updating registration', 'error')
        return redirect(url_for('admin_claim_detail', claim_id=claim_id))

@app.route('/admin/export')
@admin_required
def admin_export():
    try:
        claims_result = supabase_select('gift_claims', order_by='updated_at.desc')
        claims = claims_result if isinstance(claims_result, list) else []

        si = StringIO()
        cw = csv.writer(si)
        cw.writerow(['Registration #', 'Name', 'Email', 'Phone', 'Country', 'Address', 'City',
                     'Postal Code', 'Clothing Size', 'Status', 'Registered At'])

        for claim in claims:
            cw.writerow([
                claim.get('claim_number', ''),
                claim.get('full_name', ''),
                claim.get('email', ''),
                claim.get('phone', ''),
                claim.get('country', ''),
                claim.get('address', ''),
                claim.get('city', ''),
                claim.get('postal_code', ''),
                claim.get('clothing_size', ''),
                claim.get('status', ''),
                claim.get('claim_date', '')[:10] if claim.get('claim_date') else ''
            ])

        output = si.getvalue()
        return Response(output, mimetype='text/csv',
                       headers={'Content-Disposition': f'attachment; filename=registrations_{datetime.datetime.now().strftime("%Y%m%d")}.csv'})
    except Exception as e:
        app.logger.error(f"Export error: {str(e)}")
        flash('Error exporting', 'error')
        return redirect(url_for('admin_claims'))

@app.route('/admin/codes')
@admin_required
def admin_codes():
    try:
        codes_result = supabase_select('claim_codes', order_by='created_at.desc', limit=200)
        codes = codes_result if codes_result and isinstance(codes_result, list) else []

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
                'email': ADMIN_EMAIL
            },
            company_name=COMPANY_NAME,
            campaign_name=CAMPAIGN_NAME,
            reward_name=REWARD_NAME,
            current_year=datetime.datetime.now().year
        )
        if result:
            flash('Test email sent!', 'success')
        else:
            flash('Email failed.', 'error')
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
    print("YouTube Creator Gift Box Campaign - Registration Flow")
    print("http://localhost:5000")
    print(f"Supabase: {'Configured' if SUPABASE_URL and SUPABASE_KEY else 'Not Configured'}")
    print(f"Gmail API: {'Configured' if GMAIL_API_CLIENT_ID and GMAIL_API_REFRESH_TOKEN else 'Not Configured'}")
    print("=" * 50)
    app.run(debug=(os.getenv('FLASK_ENV') != 'production'), host='0.0.0.0', port=int(os.getenv('PORT', 5000)))