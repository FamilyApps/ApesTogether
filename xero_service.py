"""
Xero OAuth2 + Accounting API integration for influencer payouts and 1099-NEC reporting.

Handles:
- OAuth2 authorization code flow with PKCE (connect/callback/refresh)
- Creating/updating Xero contacts with W-9 tax info (legal name, TIN, address)
- Managing '1099 Contractors' contact group for 1099 report filtering
- Creating bills (Accounts Payable) from XeroPayoutRecord entries
- Syncing verified W-9 data to Xero contacts on admin approval
- Token refresh (access tokens expire every 30 min, refresh tokens last 60 days)

End-to-end 1099-NEC flow:
1. Creator submits W-9 in iOS app → admin verifies → sync_w9_to_xero_contact()
2. Monthly: generate-payout-records → sync-payouts → bills appear in Xero AP
3. Admin writes checks, marks bills paid in Xero
4. Tax season: Xero → Reports → 1099 → e-file via Tax1099/SmartFile/TaxBandits

Xero granular scopes (apps created after March 2, 2026):
- accounting.invoices → Bills, Invoices, CreditNotes
- accounting.contacts → Contacts, ContactGroups
- accounting.settings.read → Accounts, TaxRates (read-only)
- offline_access → Refresh tokens
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

# Xero OAuth2 scopes (granular — app created after March 2, 2026)
# Ref: https://developer.xero.com/documentation/guides/oauth2/scopes/
# PKCE (code_challenge + code_verifier) is required.
# Broad scope accounting.transactions is replaced by granular scopes:
#   accounting.invoices  → Invoices, Bills, CreditNotes, PurchaseOrders
#   accounting.payments  → Payments, Overpayments, Prepayments
XERO_SCOPES = ' '.join([
    'openid',
    'profile',
    'email',
    'offline_access',
    'accounting.invoices',        # Granular: Bills, Invoices, CreditNotes
    'accounting.contacts',        # Unchanged: Contacts, ContactGroups
    'accounting.settings.read',   # Unchanged: Accounts, TaxRates (read-only)
])


def _get_client_id():
    return os.environ.get('XERO_CLIENT_ID', '')


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


# ── Contact Group for 1099 Filtering ─────────────────────────────────────

_1099_group_id_cache = None

def get_or_create_1099_contact_group(token):
    """Find or create the '1099 Contractors' contact group in Xero.
    
    Xero uses contact groups to filter contacts for 1099 reporting.
    Returns the ContactGroupID string, or None on failure.
    """
    global _1099_group_id_cache
    if _1099_group_id_cache:
        return _1099_group_id_cache
    
    GROUP_NAME = '1099 Contractors'
    
    resp = _xero_get('ContactGroups', token)
    if resp.status_code == 200:
        for group in resp.json().get('ContactGroups', []):
            if group.get('Name') == GROUP_NAME and group.get('Status') == 'ACTIVE':
                _1099_group_id_cache = group['ContactGroupID']
                return _1099_group_id_cache
    
    # Create if missing
    resp = _xero_post('ContactGroups', token, {
        'ContactGroups': [{'Name': GROUP_NAME}]
    })
    if resp.status_code == 200:
        groups = resp.json().get('ContactGroups', [])
        if groups:
            _1099_group_id_cache = groups[0]['ContactGroupID']
            logger.info(f"Created Xero contact group '{GROUP_NAME}': {_1099_group_id_cache}")
            return _1099_group_id_cache
    
    logger.error(f"Failed to create 1099 contact group: {resp.status_code} {resp.text}")
    return None


def _add_contact_to_1099_group(token, contact_id):
    """Add a contact to the '1099 Contractors' group."""
    group_id = get_or_create_1099_contact_group(token)
    if not group_id:
        return False
    
    resp = requests.put(
        f"{XERO_API_BASE}/ContactGroups/{group_id}/Contacts",
        headers=_xero_headers(token),
        json={'Contacts': [{'ContactID': contact_id}]},
        timeout=15,
    )
    if resp.status_code == 200:
        logger.info(f"Added contact {contact_id} to 1099 Contractors group")
        return True
    
    logger.warning(f"Failed to add contact to 1099 group: {resp.status_code} {resp.text}")
    return False


# ── Contact Management ─────────────────────────────────────────────────────

def find_or_create_contact(token, username, email=None, w9=None):
    """Find or create a Xero contact for an influencer.
    
    When a W9Submission is provided, the contact is populated with full
    tax info (legal name, TIN, address) needed for Xero's native 1099 report.
    
    Args:
        token: Valid XeroOAuthToken
        username: Influencer's username (used as contact name)
        email: Influencer's email (optional)
        w9: W9Submission instance (optional — populates tax fields)
    
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
    
    existing_contact_id = None
    if search.status_code == 200:
        contacts = search.json().get('Contacts', [])
        if contacts:
            existing_contact_id = contacts[0]['ContactID']
    
    # Build contact payload
    contact = {
        'Name': username,
        'ContactStatus': 'ACTIVE',
        'IsSupplier': True,
    }
    if email:
        contact['EmailAddress'] = email
    
    # Populate W-9 tax info if available
    if w9:
        contact['FirstName'] = w9.legal_first_name
        contact['LastName'] = w9.legal_last_name
        
        # TaxNumber — Xero uses this for 1099 reporting (SSN or EIN)
        try:
            from services.w9_service import decrypt_tin
            tin_plain = decrypt_tin(w9.tin_encrypted)
            if w9.tin_type == 'ssn':
                contact['TaxNumber'] = f"{tin_plain[:3]}-{tin_plain[3:5]}-{tin_plain[5:]}"
            else:
                contact['TaxNumber'] = f"{tin_plain[:2]}-{tin_plain[2:]}"
        except Exception as e:
            logger.error(f"Could not decrypt TIN for Xero contact ({username}): {e}")
        
        # Address
        contact['Addresses'] = [{
            'AddressType': 'STREET',
            'AddressLine1': w9.address_line1,
            'AddressLine2': w9.address_line2 or '',
            'City': w9.city,
            'Region': w9.state,
            'PostalCode': w9.zip_code,
            'Country': 'US',
        }]
    
    if existing_contact_id:
        # Update existing contact with W-9 data
        contact['ContactID'] = existing_contact_id
        resp = _xero_post('Contacts', token, {'Contacts': [contact]})
        if resp.status_code == 200:
            logger.info(f"Updated Xero contact for {username}: {existing_contact_id}")
            if w9:
                _add_contact_to_1099_group(token, existing_contact_id)
            return existing_contact_id
        logger.error(f"Failed to update Xero contact for {username}: {resp.status_code} {resp.text}")
        return existing_contact_id  # Return ID even if update failed
    
    # Create new contact
    resp = _xero_post('Contacts', token, {'Contacts': [contact]})
    
    if resp.status_code == 200:
        new_contact = resp.json().get('Contacts', [{}])[0]
        contact_id = new_contact.get('ContactID')
        logger.info(f"Created Xero contact for {username}: {contact_id}")
        if w9:
            _add_contact_to_1099_group(token, contact_id)
        return contact_id
    
    logger.error(f"Failed to create Xero contact for {username}: {resp.status_code} {resp.text}")
    return None


# ── Bill Creation ──────────────────────────────────────────────────────────

def create_bill_for_payout(token, payout_record, username, email=None, w9=None):
    """Create a bill (Accounts Payable) in Xero for an influencer payout.
    
    Args:
        token: Valid XeroOAuthToken
        payout_record: XeroPayoutRecord instance
        username: Influencer's username
        email: Influencer's email (optional)
        w9: W9Submission instance (optional — enriches Xero contact with tax info)
    
    Returns:
        dict with 'invoice_id' and 'contact_id' on success, or 'error' on failure
    """
    from models import AdminSubscription
    
    # Ensure we have a contact (with W-9 data if available)
    contact_id = payout_record.xero_contact_id
    if not contact_id:
        contact_id = find_or_create_contact(token, username, email, w9=w9)
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
    
    from models import W9Submission
    
    # Get pending payout records (skip held — those need a W-9 first)
    query = XeroPayoutRecord.query.filter_by(xero_sync_status='pending').filter(
        XeroPayoutRecord.payment_status != 'held'
    )
    if period_start:
        query = query.filter_by(period_start=period_start)
    if period_end:
        query = query.filter_by(period_end=period_end)
    
    records = query.all()
    
    results = {
        'synced': [],
        'failed': [],
        'skipped': 0,
        'held': 0,
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
        
        # Get W-9 for contact enrichment (best-effort — bill still created without it)
        w9 = W9Submission.query.filter_by(user_id=record.portfolio_user_id).filter(
            W9Submission.status.in_(['submitted', 'verified'])
        ).order_by(W9Submission.created_at.desc()).first()
        
        email = getattr(user, 'email', None)
        bill_result = create_bill_for_payout(token, record, user.username, email, w9=w9)
        
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


# ── W-9 → Xero Contact Sync ────────────────────────────────────────────────

def sync_w9_to_xero_contact(user_id):
    """When a W-9 is verified, sync the creator's tax info to Xero.
    
    Creates or updates their Xero contact with legal name, TIN, address,
    and adds them to the '1099 Contractors' contact group.
    
    Args:
        user_id: User ID of the influencer
    
    Returns:
        dict with 'contact_id' on success, or 'error' on failure
    """
    from models import User, W9Submission
    
    token = get_valid_token()
    if not token:
        return {'error': 'No valid Xero token — connect at /admin/xero/connect first'}
    
    user = User.query.get(user_id)
    if not user:
        return {'error': f'User {user_id} not found'}
    
    w9 = W9Submission.query.filter_by(user_id=user_id).filter(
        W9Submission.status.in_(['submitted', 'verified'])
    ).order_by(W9Submission.created_at.desc()).first()
    
    if not w9:
        return {'error': f'No active W-9 for user {user_id}'}
    
    contact_id = find_or_create_contact(
        token,
        user.username,
        email=user.email,
        w9=w9,
    )
    
    if contact_id:
        logger.info(f"W-9 synced to Xero contact for {user.username} (contact_id={contact_id})")
        return {'contact_id': contact_id, 'username': user.username}
    
    return {'error': f'Failed to create/update Xero contact for {user.username}'}


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
