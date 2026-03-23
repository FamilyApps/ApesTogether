"""
Xero OAuth2 + Accounting API integration for influencer payouts.

Handles:
- OAuth2 authorization code flow (connect/callback/refresh)
- Creating contacts in Xero for influencers
- Creating bills (Accounts Payable) from XeroPayoutRecord entries
- Token refresh (access tokens expire every 30 min, refresh tokens last 60 days)

Xero granular scopes (apps created after March 2, 2026):
- accounting.transactions.read / .create
- accounting.contacts.read / .create
- accounting.settings.read
- offline_access (for refresh tokens)
"""

import os
import base64
import hashlib
import secrets
import logging
import requests
from datetime import datetime, timedelta
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Xero OAuth2 endpoints
XERO_AUTH_URL = 'https://login.xero.com/identity/connect/authorize'
XERO_TOKEN_URL = 'https://identity.xero.com/connect/token'
XERO_CONNECTIONS_URL = 'https://api.xero.com/connections'
XERO_API_BASE = 'https://api.xero.com/api.xro/2.0'

# Xero OAuth2 scopes — granular (required for apps created after March 2, 2026)
# Ref: https://developer.xero.com/documentation/guides/oauth2/scopes/
# DEBUG: Using minimal scopes to isolate auth error. Will add accounting scopes
# back once the OAuth flow works.
XERO_SCOPES = ' '.join([
    'openid',
    'profile',
    'email',
    'offline_access',
])


def _get_client_id():
    # Xero client IDs are UUIDs — ensure lowercase for compatibility
    return os.environ.get('XERO_CLIENT_ID', '').lower()


def _get_client_secret():
    return os.environ.get('XERO_CLIENT_SECRET', '')


def _get_redirect_uri():
    return os.environ.get('XERO_REDIRECT_URI', 'https://apestogether.ai/api/mobile/admin/xero/callback')


def _basic_auth_header():
    """Xero requires client_id:client_secret as Basic auth for token requests."""
    creds = f"{_get_client_id()}:{_get_client_secret()}"
    encoded = base64.b64encode(creds.encode()).decode()
    return f"Basic {encoded}"


# ── Token Management ──────────────────────────────────────────────────────

def get_stored_token():
    """Get the stored Xero OAuth token from the database."""
    from models import XeroOAuthToken
    return XeroOAuthToken.query.first()


def get_valid_token():
    """Get a valid (non-expired) access token, refreshing if necessary.
    
    Returns:
        XeroOAuthToken or None if no token exists / refresh fails
    """
    token = get_stored_token()
    if not token:
        logger.warning("No Xero OAuth token stored — need to connect first")
        return None
    
    if token.is_expired:
        logger.info("Xero access token expired, refreshing...")
        token = refresh_access_token(token)
    
    return token


def store_token(token_data, tenant_id=None):
    """Store or update the Xero OAuth token in the database.
    
    Args:
        token_data: dict from Xero token endpoint response
        tenant_id: Xero tenant/org ID (from /connections endpoint)
    """
    from models import db, XeroOAuthToken
    
    token = XeroOAuthToken.query.first()
    expires_at = datetime.utcnow() + timedelta(seconds=token_data.get('expires_in', 1800))
    
    if token:
        token.access_token = token_data['access_token']
        token.refresh_token = token_data['refresh_token']
        token.token_type = token_data.get('token_type', 'Bearer')
        token.expires_at = expires_at
        token.scopes = token_data.get('scope', '')
        if tenant_id:
            token.tenant_id = tenant_id
    else:
        token = XeroOAuthToken(
            access_token=token_data['access_token'],
            refresh_token=token_data['refresh_token'],
            token_type=token_data.get('token_type', 'Bearer'),
            expires_at=expires_at,
            tenant_id=tenant_id,
            scopes=token_data.get('scope', ''),
        )
        db.session.add(token)
    
    db.session.commit()
    logger.info(f"Xero token stored (expires {expires_at.isoformat()})")
    return token


def refresh_access_token(token):
    """Refresh the Xero access token using the refresh token.
    
    Returns:
        Updated XeroOAuthToken or None on failure
    """
    resp = requests.post(
        XERO_TOKEN_URL,
        headers={
            'Authorization': _basic_auth_header(),
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        data={
            'grant_type': 'refresh_token',
            'refresh_token': token.refresh_token,
        },
        timeout=15,
    )
    
    if resp.status_code != 200:
        logger.error(f"Xero token refresh failed ({resp.status_code}): {resp.text}")
        return None
    
    data = resp.json()
    return store_token(data, tenant_id=token.tenant_id)


# ── OAuth2 Authorization Flow ─────────────────────────────────────────────

def get_authorization_url(state=None):
    """Build the Xero OAuth2 authorization URL with PKCE.
    
    Args:
        state: CSRF token (stored in session for verification)
    
    Returns:
        (url, state, code_verifier) tuple — caller must store code_verifier in session
    """
    if not state:
        state = secrets.token_urlsafe(32)
    
    # PKCE: generate code_verifier and derive code_challenge (S256)
    code_verifier = secrets.token_urlsafe(64)  # 43-128 chars per RFC 7636
    challenge_digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_digest).rstrip(b'=').decode('ascii')
    
    params = {
        'response_type': 'code',
        'client_id': _get_client_id(),
        'redirect_uri': _get_redirect_uri(),
        'scope': XERO_SCOPES,
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
    }
    
    url = f"{XERO_AUTH_URL}?{urlencode(params)}"
    logger.info(f"Xero auth URL (PKCE): redirect_uri={params['redirect_uri']} scopes={params['scope']} client_id={params['client_id'][:8]}...")
    return url, state, code_verifier


def exchange_code_for_token(code, code_verifier=None):
    """Exchange the authorization code for access + refresh tokens.
    
    Args:
        code: Authorization code from Xero callback
        code_verifier: PKCE code verifier (stored in session during /connect)
    
    Returns:
        XeroOAuthToken on success, None on failure
    """
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': _get_redirect_uri(),
    }
    if code_verifier:
        data['code_verifier'] = code_verifier
    
    resp = requests.post(
        XERO_TOKEN_URL,
        headers={
            'Authorization': _basic_auth_header(),
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        data=data,
        timeout=15,
    )
    
    if resp.status_code != 200:
        logger.error(f"Xero code exchange failed ({resp.status_code}): {resp.text}")
        return None
    
    token_data = resp.json()
    
    # Get the tenant ID from /connections
    tenant_id = _fetch_tenant_id(token_data['access_token'])
    
    return store_token(token_data, tenant_id=tenant_id)


def _fetch_tenant_id(access_token):
    """Fetch the connected Xero organisation's tenant ID."""
    resp = requests.get(
        XERO_CONNECTIONS_URL,
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=10,
    )
    
    if resp.status_code == 200:
        connections = resp.json()
        if connections:
            tenant_id = connections[0]['tenantId']
            logger.info(f"Xero tenant ID: {tenant_id} ({connections[0].get('tenantName', 'unknown')})")
            return tenant_id
    
    logger.error(f"Failed to fetch Xero tenant ID: {resp.status_code} {resp.text}")
    return None


# ── Xero API Helpers ───────────────────────────────────────────────────────

def _xero_headers(token):
    """Standard headers for Xero API calls."""
    return {
        'Authorization': f'Bearer {token.access_token}',
        'Xero-tenant-id': token.tenant_id,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }


def _xero_get(endpoint, token):
    """GET request to Xero API with auto token refresh."""
    resp = requests.get(
        f"{XERO_API_BASE}/{endpoint}",
        headers=_xero_headers(token),
        timeout=15,
    )
    return resp


def _xero_post(endpoint, token, json_data):
    """POST request to Xero API with auto token refresh."""
    resp = requests.post(
        f"{XERO_API_BASE}/{endpoint}",
        headers=_xero_headers(token),
        json=json_data,
        timeout=15,
    )
    return resp


# ── Contact Management ─────────────────────────────────────────────────────

def find_or_create_contact(token, username, email=None):
    """Find or create a Xero contact for an influencer.
    
    Args:
        token: Valid XeroOAuthToken
        username: Influencer's username (used as contact name)
        email: Influencer's email (optional, for matching)
    
    Returns:
        Xero ContactID string, or None on failure
    """
    # Try to find by name first
    search = requests.get(
        f"{XERO_API_BASE}/Contacts",
        headers=_xero_headers(token),
        params={'where': f'Name=="{username}"'},
        timeout=15,
    )
    
    if search.status_code == 200:
        contacts = search.json().get('Contacts', [])
        if contacts:
            return contacts[0]['ContactID']
    
    # Create new contact
    contact_data = {
        'Contacts': [{
            'Name': username,
            'ContactStatus': 'ACTIVE',
            'IsSupplier': True,
        }]
    }
    if email:
        contact_data['Contacts'][0]['EmailAddress'] = email
    
    resp = _xero_post('Contacts', token, contact_data)
    
    if resp.status_code == 200:
        new_contact = resp.json().get('Contacts', [{}])[0]
        contact_id = new_contact.get('ContactID')
        logger.info(f"Created Xero contact for {username}: {contact_id}")
        return contact_id
    
    logger.error(f"Failed to create Xero contact for {username}: {resp.status_code} {resp.text}")
    return None


# ── Bill Creation ──────────────────────────────────────────────────────────

def create_bill_for_payout(token, payout_record, username, email=None):
    """Create a bill (Accounts Payable) in Xero for an influencer payout.
    
    Args:
        token: Valid XeroOAuthToken
        payout_record: XeroPayoutRecord instance
        username: Influencer's username
        email: Influencer's email (optional)
    
    Returns:
        dict with 'invoice_id' and 'contact_id' on success, or 'error' on failure
    """
    from models import AdminSubscription
    
    # Ensure we have a contact
    contact_id = payout_record.xero_contact_id
    if not contact_id:
        contact_id = find_or_create_contact(token, username, email)
        if not contact_id:
            return {'error': f'Failed to find/create Xero contact for {username}'}
    
    # Build line items
    line_items = []
    payout_per_sub = AdminSubscription.INFLUENCER_PAYOUT_PER_SUB  # $6.50
    
    if payout_record.real_subscriber_count > 0:
        line_items.append({
            'Description': f'Influencer payout — {payout_record.real_subscriber_count} real subscriber(s) @ ${payout_per_sub:.2f}',
            'Quantity': payout_record.real_subscriber_count,
            'UnitAmount': payout_per_sub,
            'AccountCode': '6000',  # Cost of Revenue (adjust to your chart of accounts)
            'TaxType': 'NONE',
        })
    
    if payout_record.bonus_subscriber_count > 0:
        line_items.append({
            'Description': f'Promotional payout — {payout_record.bonus_subscriber_count} bonus subscriber(s) @ ${payout_per_sub:.2f}',
            'Quantity': payout_record.bonus_subscriber_count,
            'UnitAmount': payout_per_sub,
            'AccountCode': '6100',  # Marketing / Promotion expense (adjust to your chart of accounts)
            'TaxType': 'NONE',
        })
    
    if not line_items:
        return {'error': 'No line items to bill (0 subscribers)'}
    
    # Due date: 30 days from now
    due_date = (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d')
    period_label = f"{payout_record.period_start.strftime('%b %Y')}"
    
    bill_data = {
        'Invoices': [{
            'Type': 'ACCPAY',  # Accounts Payable = bill
            'Contact': {'ContactID': contact_id},
            'Date': datetime.utcnow().strftime('%Y-%m-%d'),
            'DueDate': due_date,
            'Reference': f'Payout-{username}-{period_label}',
            'Status': 'AUTHORISED',
            'CurrencyCode': 'USD',
            'LineItems': line_items,
        }]
    }
    
    resp = _xero_post('Invoices', token, bill_data)
    
    if resp.status_code == 200:
        invoice = resp.json().get('Invoices', [{}])[0]
        invoice_id = invoice.get('InvoiceID')
        logger.info(f"Created Xero bill for {username}: {invoice_id} (${payout_record.total_payout:.2f})")
        return {
            'invoice_id': invoice_id,
            'contact_id': contact_id,
        }
    
    error = resp.text[:500]
    logger.error(f"Xero bill creation failed for {username}: {resp.status_code} {error}")
    return {'error': f'Xero API error {resp.status_code}: {error}'}


# ── Sync Payout Records to Xero ───────────────────────────────────────────

def sync_payout_records_to_xero(period_start=None, period_end=None):
    """Sync pending XeroPayoutRecord entries as bills in Xero.
    
    Args:
        period_start: Only sync records for this period (date)
        period_end: Only sync records for this period (date)
    
    Returns:
        dict with 'synced', 'failed', 'skipped', 'total_amount'
    """
    from models import db, User, XeroPayoutRecord, XeroSyncLog
    
    token = get_valid_token()
    if not token:
        return {'error': 'No valid Xero token — connect at /admin/xero/connect first'}
    
    # Get pending payout records
    query = XeroPayoutRecord.query.filter_by(xero_sync_status='pending')
    if period_start:
        query = query.filter_by(period_start=period_start)
    if period_end:
        query = query.filter_by(period_end=period_end)
    
    records = query.all()
    
    results = {
        'synced': [],
        'failed': [],
        'skipped': 0,
        'total_amount': 0.0,
    }
    
    for record in records:
        user = User.query.get(record.portfolio_user_id)
        if not user:
            results['skipped'] += 1
            continue
        
        # Skip bots
        if hasattr(user, 'role') and user.role == 'agent':
            results['skipped'] += 1
            continue
        
        email = getattr(user, 'email', None)
        bill_result = create_bill_for_payout(token, record, user.username, email)
        
        if 'error' in bill_result:
            record.xero_sync_status = 'failed'
            record.xero_error = bill_result['error']
            results['failed'].append({
                'user_id': record.portfolio_user_id,
                'username': user.username,
                'error': bill_result['error'],
            })
            
            # Log failure
            log = XeroSyncLog(
                sync_type='monthly_payout',
                entity_id=record.id,
                entity_type='xero_payout_record',
                amount=record.total_payout,
                status='failed',
                error_message=bill_result['error'],
            )
            db.session.add(log)
        else:
            record.xero_invoice_id = bill_result['invoice_id']
            record.xero_contact_id = bill_result['contact_id']
            record.xero_sync_status = 'synced'
            record.xero_synced_at = datetime.utcnow()
            results['synced'].append({
                'user_id': record.portfolio_user_id,
                'username': user.username,
                'invoice_id': bill_result['invoice_id'],
                'amount': record.total_payout,
            })
            results['total_amount'] += record.total_payout
            
            # Log success
            log = XeroSyncLog(
                sync_type='monthly_payout',
                entity_id=record.id,
                entity_type='xero_payout_record',
                xero_invoice_id=bill_result['invoice_id'],
                xero_contact_id=bill_result['contact_id'],
                amount=record.total_payout,
                status='success',
            )
            db.session.add(log)
    
    db.session.commit()
    
    logger.info(
        f"Xero sync complete: {len(results['synced'])} synced, "
        f"{len(results['failed'])} failed, {results['skipped']} skipped, "
        f"${results['total_amount']:.2f} total"
    )
    
    return results


def get_xero_status():
    """Get the current status of the Xero connection."""
    token = get_stored_token()
    
    if not token:
        return {
            'connected': False,
            'message': 'No Xero connection — visit /admin/xero/connect',
        }
    
    return {
        'connected': True,
        'tenant_id': token.tenant_id,
        'token_valid': not token.is_expired,
        'expires_at': token.expires_at.isoformat() if token.expires_at else None,
        'last_updated': token.updated_at.isoformat() if token.updated_at else None,
    }
