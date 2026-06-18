"""
Xero OAuth2 + Accounting API integration for influencer payouts and 1099-NEC reporting.

Handles:
- OAuth2 authorization code flow with PKCE (connect/callback/refresh)
- Creating/updating Xero contacts for influencers
- Managing '1099 Contractors' contact group (for the year-end 1099 report)
- Pushing in-app W-9 data (legal name, address, TIN) onto the Xero contact
- Checking if a contact has a TaxNumber on file (payout hold logic)
- Creating bills (Accounts Payable) from XeroPayoutRecord entries
- Token refresh (access tokens expire every 30 min, refresh tokens last 60 days)

End-to-end 1099-NEC flow:
1. Creator becomes payout-eligible → app prompts for W-9 (legal name, address, TIN)
2. App pushes W-9 to the Xero contact (TaxNumber + address) and adds it to the
   '1099 Contractors' group. NOTE: Xero does NOT email contractors for a W-9 —
   collection is done in-app; Xero only stores the TaxNumber and runs the report.
3. Monthly: generate-payout-records → sync-payouts → bills appear in Xero AP
4. Payouts HELD (not synced/paid) until the contact has a TaxNumber
   (contact_has_tax_number()); released automatically once the W-9 is on file.
5. Admin pays bills in Xero → marks as paid
6. Tax season: Xero → Reports → 1099 → e-file via Tax1099/SmartFile/TaxBandits

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

def find_or_create_contact(token, username, email=None):
    """Find or create a Xero contact for an influencer.
    
    All creators are added to the '1099 Contractors' contact group.
    W-9 data (TIN, legal name, address) is collected in-app and pushed onto
    the contact via update_contact_tax_info(); Xero does NOT solicit it.
    
    Args:
        token: Valid XeroOAuthToken
        username: Influencer's username (used as contact name)
        email: Influencer's email (optional)
    
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
    
    if existing_contact_id:
        contact['ContactID'] = existing_contact_id
        resp = _xero_post('Contacts', token, {'Contacts': [contact]})
        if resp.status_code == 200:
            logger.info(f"Updated Xero contact for {username}: {existing_contact_id}")
        else:
            logger.error(f"Failed to update Xero contact for {username}: {resp.status_code} {resp.text}")
        # Always add to 1099 group (idempotent)
        _add_contact_to_1099_group(token, existing_contact_id)
        return existing_contact_id
    
    # Create new contact
    resp = _xero_post('Contacts', token, {'Contacts': [contact]})
    
    if resp.status_code == 200:
        new_contact = resp.json().get('Contacts', [{}])[0]
        contact_id = new_contact.get('ContactID')
        logger.info(f"Created Xero contact for {username}: {contact_id}")
        _add_contact_to_1099_group(token, contact_id)
        return contact_id
    
    logger.error(f"Failed to create Xero contact for {username}: {resp.status_code} {resp.text}")
    return None


def contact_has_tax_number(username):
    """Check if a Xero contact has a TaxNumber (TIN) on file.
    
    Used to determine if payouts should be held — the TaxNumber is set from the
    creator's in-app W-9 submission (see update_contact_tax_info()).
    
    Returns:
        True if the contact exists and has a TaxNumber set, False otherwise.
    """
    token = get_valid_token()
    if not token:
        return False
    
    try:
        resp = requests.get(
            f"{XERO_API_BASE}/Contacts",
            headers=_xero_headers(token),
            params={'where': f'Name=="{username}"'},
            timeout=15,
        )
        if resp.status_code == 200:
            contacts = resp.json().get('Contacts', [])
            if contacts:
                tax_number = contacts[0].get('TaxNumber', '')
                return bool(tax_number and tax_number.strip())
    except Exception as e:
        logger.error(f"Xero contact tax check failed for {username}: {e}")
    
    return False


def reconcile_w9_on_file(username, token=None):
    """Re-check Xero for a creator's TaxNumber (TIN) and return its contact id.

    Used by the W-9 retry job. Because the full TIN is never stored locally
    (PII minimization), a failed push can't be re-sent from our DB — instead we
    reconcile against Xero's authoritative state: if the contact now has a
    TaxNumber (the original push actually landed, or it was added manually), the
    creator is on file and held payouts can be released.

    Returns {'on_file': bool, 'contact_id': str|None}, or {'error': ...}.
    """
    if token is None:
        token = get_valid_token()
    if not token:
        return {'error': 'No valid Xero token — connect at /api/mobile/admin/xero/connect first'}
    try:
        resp = requests.get(
            f"{XERO_API_BASE}/Contacts",
            headers=_xero_headers(token),
            params={'where': f'Name=="{username}"'},
            timeout=15,
        )
        if resp.status_code == 200:
            contacts = resp.json().get('Contacts', [])
            if contacts:
                c = contacts[0]
                tax_number = (c.get('TaxNumber') or '').strip()
                return {'on_file': bool(tax_number), 'contact_id': c.get('ContactID')}
        return {'on_file': False, 'contact_id': None}
    except Exception as e:
        logger.error(f"W-9 reconcile failed for {username}: {e}")
        return {'error': str(e)}


def update_contact_tax_info(username, email, w9):
    """Push in-app W-9 data onto the creator's Xero contact.

    Sets the TaxNumber (TIN), legal name, and mailing address on the contact,
    marks it a supplier, and ensures it's in the '1099 Contractors' group.

    Args:
        username: creator's username (stable Xero contact Name — used for matching)
        email: creator's email (optional)
        w9: dict with keys legal_name, business_name, tin (full digits),
            address_line1, address_line2, city, state, postal_code, country

    Returns:
        {'contact_id': ...} on success, or {'error': ...} on failure.
    """
    token = get_valid_token()
    if not token:
        return {'error': 'No valid Xero token — connect at /api/mobile/admin/xero/connect first'}

    # Keep Name == username for stable matching; identity goes in First/Last name.
    contact_id = find_or_create_contact(token, username, email)
    if not contact_id:
        return {'error': f'Failed to find/create Xero contact for {username}'}

    contact = {
        'ContactID': contact_id,
        'TaxNumber': (w9.get('tin') or '').strip(),
        'IsSupplier': True,
        'Addresses': [{
            'AddressType': 'STREET',
            'AddressLine1': w9.get('address_line1') or '',
            'AddressLine2': w9.get('address_line2') or '',
            'City': w9.get('city') or '',
            'Region': w9.get('state') or '',
            'PostalCode': w9.get('postal_code') or '',
            'Country': w9.get('country') or 'US',
        }],
    }

    # Split legal name into First/Last for 1099 reporting (best effort).
    legal = (w9.get('legal_name') or '').strip()
    if legal:
        parts = legal.split()
        contact['FirstName'] = parts[0]
        if len(parts) > 1:
            contact['LastName'] = ' '.join(parts[1:])

    resp = _xero_post('Contacts', token, {'Contacts': [contact]})
    if resp.status_code == 200:
        _add_contact_to_1099_group(token, contact_id)
        logger.info(f"Pushed W-9 tax info to Xero contact for {username}: {contact_id}")
        return {'contact_id': contact_id}

    error = resp.text[:500]
    logger.error(f"Xero W-9 push failed for {username}: {resp.status_code} {error}")
    return {'error': f'Xero API error {resp.status_code}: {error}'}


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
    
    # Ensure we have a contact (with W-9 data if available)
    contact_id = payout_record.xero_contact_id
    if not contact_id:
        contact_id = find_or_create_contact(token, username, email)
        if not contact_id:
            return {'error': f'Failed to find/create Xero contact for {username}'}
    
    # Build line items from the record's ACTUAL dollar amounts (transaction-driven
    # and already net of any refund clawback), NOT count×rate — annual subs and
    # clawbacks make the per-sub rate wrong as a multiplier.
    line_items = []

    # Both real and bonus/gifted payouts are nonemployee compensation paid to the
    # creator, so BOTH are 1099-reportable and post to 6010 (User Payments) under
    # the creator's contact. (Previously real->6000 [nonexistent] and bonus->6100
    # [that's the store-fee account] — both were wrong.)
    PAYOUT_ACCOUNT_CODE = '6010'  # User Payments (creator payouts / contract labor)

    real_amt = round(float(payout_record.influencer_payout or 0.0), 2)
    bonus_amt = round(float(payout_record.bonus_payout or 0.0), 2)

    if real_amt > 0:
        line_items.append({
            'Description': f'Influencer payout — {payout_record.real_subscriber_count} subscriber transaction(s), net of refunds',
            'Quantity': 1,
            'UnitAmount': real_amt,
            'AccountCode': PAYOUT_ACCOUNT_CODE,
            'TaxType': 'NONE',
        })

    if bonus_amt > 0:
        line_items.append({
            'Description': f'Promotional payout — {payout_record.bonus_subscriber_count} bonus subscriber(s)',
            'Quantity': 1,
            'UnitAmount': bonus_amt,
            'AccountCode': PAYOUT_ACCOUNT_CODE,
            'TaxType': 'NONE',
        })
    
    if not line_items:
        return {'error': 'No line items to bill (zero net payout)'}
    
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
        return {'error': 'No valid Xero token — connect at /api/mobile/admin/xero/connect first'}
    
    # Get pending payout records (skip held — those need tax info first)
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
            'message': 'No Xero connection — visit /api/mobile/admin/xero/connect',
        }
    
    return {
        'connected': True,
        'tenant_id': token.tenant_id,
        'token_valid': not token.is_expired,
        'expires_at': token.expires_at.isoformat() if token.expires_at else None,
        'last_updated': token.updated_at.isoformat() if token.updated_at else None,
    }


# ── Chart of Accounts (read-only) ─────────────────────────────────────────

def list_accounts(token=None):
    """Fetch the connected org's chart of accounts (read-only).

    Uses the already-granted accounting.settings.read scope. Returns
    {'accounts': [...], 'count': N} where each account is
    {code, name, type, class, status, tax_type, description}, or {'error': ...}.

    Use this to discover which account codes to post revenue / store fees /
    payouts to (the codes differ per Xero organisation's chart of accounts).
    """
    if token is None:
        token = get_valid_token()
    if not token:
        return {'error': 'No valid Xero token — connect at /api/mobile/admin/xero/connect first'}

    resp = _xero_get('Accounts', token)
    if resp.status_code != 200:
        logger.error(f"Xero list accounts failed: {resp.status_code} {resp.text[:300]}")
        return {'error': f'Xero API error {resp.status_code}: {resp.text[:300]}'}

    accounts = []
    for a in resp.json().get('Accounts', []):
        accounts.append({
            'code': a.get('Code'),
            'name': a.get('Name'),
            'type': a.get('Type'),          # e.g. SALES, REVENUE, EXPENSE, DIRECTCOSTS
            'class': a.get('Class'),        # ASSET, EQUITY, EXPENSE, LIABILITY, REVENUE
            'status': a.get('Status'),
            'tax_type': a.get('TaxType'),
            'description': a.get('Description'),
        })
    accounts.sort(key=lambda x: ((x['class'] or 'ZZZ'), (x['code'] or 'zzz')))
    return {'accounts': accounts, 'count': len(accounts)}


# ── Subscription Revenue + Store Fees (gross/principal posting) ─────────────

# Confirm these exist via /admin/xero/accounts before the first real posting.
REVENUE_ACCOUNT_CODE = '4010'    # Subscription Revenue (income)
STORE_FEE_ACCOUNT_CODE = '6100'  # Apple/Google store fees (expense)

_STORE_CONTACT_NAMES = {
    'apple': 'Apple App Store',
    'google': 'Google Play',
}


def _period_entity_id(platform, period_start):
    """Deterministic XeroSyncLog.entity_id for a (platform, month) so re-runs are
    idempotent. e.g. apple 2026-03 -> 2026031."""
    idx = {'apple': 1, 'google': 2}.get(platform, 9)
    return int(period_start.strftime('%Y%m')) * 10 + idx


def _period_already_posted(sync_type, entity_id):
    from models import XeroSyncLog
    return XeroSyncLog.query.filter_by(
        sync_type=sync_type, entity_id=entity_id, status='success'
    ).first() is not None


def find_or_create_store_contact(token, platform):
    """Find/create the storefront counterparty contact (NOT in the 1099 group)."""
    name = _STORE_CONTACT_NAMES.get(platform, platform.title())
    search = requests.get(
        f"{XERO_API_BASE}/Contacts",
        headers=_xero_headers(token),
        params={'where': f'Name=="{name}"'},
        timeout=15,
    )
    if search.status_code == 200:
        contacts = search.json().get('Contacts', [])
        if contacts:
            return contacts[0]['ContactID']
    resp = _xero_post('Contacts', token, {'Contacts': [{
        'Name': name,
        'ContactStatus': 'ACTIVE',
        'IsCustomer': True,
        'IsSupplier': True,
    }]})
    if resp.status_code == 200:
        c = resp.json().get('Contacts', [{}])[0]
        logger.info(f"Created Xero store contact '{name}': {c.get('ContactID')}")
        return c.get('ContactID')
    logger.error(f"Failed to create store contact '{name}': {resp.status_code} {resp.text[:300]}")
    return None


def post_subscription_revenue(period_start, period_end):
    """Post gross subscription revenue (4010) and store fees (6100) for a period,
    summed transaction-by-transaction from InAppPurchase (annual-aware).

    Gross/principal: the FULL price is booked as revenue and the store fee as an
    expense. Per platform we create one ACCREC invoice (line 4010 = gross) and one
    ACCPAY bill (line 6100 = store fee) against an "Apple App Store" / "Google Play"
    contact, so net (invoice − bill) equals the deposit you reconcile in the bank.

    Idempotent: a deterministic period key + XeroSyncLog guard prevent double
    posting; re-running only posts platforms/periods not already 'success'.
    """
    from models import db, InAppPurchase, XeroSyncLog
    from sqlalchemy import func

    token = get_valid_token()
    if not token:
        return {'error': 'No valid Xero token — connect at /api/mobile/admin/xero/connect first'}

    results = {'posted': [], 'skipped': [], 'failed': [], 'gross': 0.0, 'store_fees': 0.0}
    period_key = period_start.strftime('%Y-%m')
    start_dt = datetime.combine(period_start, datetime.min.time())
    end_dt = datetime.combine(period_end, datetime.max.time())

    for platform in ('apple', 'google'):
        gross, store_fee, txn_count = db.session.query(
            func.coalesce(func.sum(InAppPurchase.price), 0.0),
            func.coalesce(func.sum(InAppPurchase.store_fee), 0.0),
            func.count(InAppPurchase.id),
        ).filter(
            InAppPurchase.platform == platform,
            InAppPurchase.status != 'refunded',
            InAppPurchase.purchase_date >= start_dt,
            InAppPurchase.purchase_date <= end_dt,
        ).one()
        gross, store_fee, txn_count = float(gross), float(store_fee), int(txn_count)

        if txn_count == 0 or gross <= 0:
            results['skipped'].append({'platform': platform, 'reason': 'no_transactions'})
            continue

        entity_id = _period_entity_id(platform, period_start)
        if _period_already_posted('subscription_revenue', entity_id):
            results['skipped'].append({'platform': platform, 'reason': 'already_posted'})
            continue

        contact_id = find_or_create_store_contact(token, platform)
        if not contact_id:
            results['failed'].append({'platform': platform, 'error': 'contact_failed'})
            continue

        store_label = _STORE_CONTACT_NAMES.get(platform, platform.title())
        date_str = period_end.strftime('%Y-%m-%d')

        # 1) Revenue — ACCREC invoice (income to 4010)
        inv = _xero_post('Invoices', token, {'Invoices': [{
            'Type': 'ACCREC',
            'Contact': {'ContactID': contact_id},
            'Date': date_str,
            'DueDate': date_str,
            'Reference': f"Rev-{platform}-{period_key}",
            'Status': 'AUTHORISED',
            'CurrencyCode': 'USD',
            'LineItems': [{
                'Description': f'{store_label} subscription revenue — {period_key} ({txn_count} txns)',
                'Quantity': 1,
                'UnitAmount': round(gross, 2),
                'AccountCode': REVENUE_ACCOUNT_CODE,
                'TaxType': 'NONE',
            }],
        }]})
        if inv.status_code != 200:
            err = inv.text[:300]
            results['failed'].append({'platform': platform, 'stage': 'revenue', 'error': err})
            db.session.add(XeroSyncLog(
                sync_type='subscription_revenue', entity_id=entity_id, entity_type='revenue',
                amount=gross, status='failed', error_message=err))
            db.session.commit()
            continue
        rev_invoice_id = inv.json().get('Invoices', [{}])[0].get('InvoiceID')

        # 2) Store fee — ACCPAY bill (expense to 6100)
        fee_bill_id = None
        if store_fee > 0:
            bill = _xero_post('Invoices', token, {'Invoices': [{
                'Type': 'ACCPAY',
                'Contact': {'ContactID': contact_id},
                'Date': date_str,
                'DueDate': date_str,
                'Reference': f"Fee-{platform}-{period_key}",
                'Status': 'AUTHORISED',
                'CurrencyCode': 'USD',
                'LineItems': [{
                    'Description': f'{store_label} commission/store fee — {period_key}',
                    'Quantity': 1,
                    'UnitAmount': round(store_fee, 2),
                    'AccountCode': STORE_FEE_ACCOUNT_CODE,
                    'TaxType': 'NONE',
                }],
            }]})
            if bill.status_code == 200:
                fee_bill_id = bill.json().get('Invoices', [{}])[0].get('InvoiceID')
            else:
                results['failed'].append({'platform': platform, 'stage': 'store_fee', 'error': bill.text[:300]})

        db.session.add(XeroSyncLog(
            sync_type='subscription_revenue', entity_id=entity_id, entity_type='revenue',
            xero_invoice_id=rev_invoice_id, xero_contact_id=contact_id, amount=gross, status='success'))
        if fee_bill_id:
            db.session.add(XeroSyncLog(
                sync_type='store_fee', entity_id=entity_id, entity_type='fee',
                xero_invoice_id=fee_bill_id, xero_contact_id=contact_id, amount=store_fee, status='success'))
        db.session.commit()

        results['posted'].append({
            'platform': platform, 'period': period_key, 'transactions': txn_count,
            'gross_revenue': round(gross, 2), 'store_fee': round(store_fee, 2),
            'net': round(gross - store_fee, 2),
            'revenue_invoice_id': rev_invoice_id, 'store_fee_bill_id': fee_bill_id,
        })
        results['gross'] += gross
        results['store_fees'] += store_fee

    results['gross'] = round(results['gross'], 2)
    results['store_fees'] = round(results['store_fees'], 2)
    results['net'] = round(results['gross'] - results['store_fees'], 2)
    return results


# ── Refund / chargeback reversal (credit notes) ────────────────────────────

def _refund_entity_id(purchase_id):
    """Per-purchase idempotency key for refund reversals."""
    return int(purchase_id)


def reverse_refunded_purchase(purchase, token=None):
    """Reverse the Xero revenue + store fee for ONE refunded InAppPurchase.

    Why this is needed: `post_subscription_revenue` books gross revenue (4010)
    and store fees (6100) per period and EXCLUDES `status == 'refunded'` rows.
    So a refund that lands BEFORE that period is posted needs no reversal (the
    row is simply never booked). But a refund that lands AFTER the period was
    already posted (e.g. a late chargeback) leaves revenue overstated — this
    issues credit notes to reverse exactly that transaction's revenue + fee.

    Idempotent: a per-purchase XeroSyncLog guard (sync_type='subscription_refund')
    prevents double-reversal. Returns a dict describing what happened.
    """
    from models import db, XeroSyncLog
    from datetime import date as _date

    entity_id = _refund_entity_id(purchase.id)
    if _period_already_posted('subscription_refund', entity_id):
        return {'skipped': 'already_reversed', 'purchase_id': purchase.id}

    pdate = purchase.purchase_date.date() if hasattr(purchase.purchase_date, 'date') else purchase.purchase_date
    period_start = _date(pdate.year, pdate.month, 1)

    # Only reverse if the original revenue was actually posted; otherwise the
    # refunded row is already excluded from posting and there is nothing to undo.
    if not _period_already_posted('subscription_revenue', _period_entity_id(purchase.platform, period_start)):
        return {'skipped': 'revenue_not_posted', 'purchase_id': purchase.id}

    if token is None:
        token = get_valid_token()
    if not token:
        return {'error': 'No valid Xero token — connect at /api/mobile/admin/xero/connect first'}

    contact_id = find_or_create_store_contact(token, purchase.platform)
    if not contact_id:
        return {'error': 'store_contact_failed', 'purchase_id': purchase.id}

    store_label = _STORE_CONTACT_NAMES.get(purchase.platform, purchase.platform.title())
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    period_key = period_start.strftime('%Y-%m')
    price = round(float(purchase.price or 0.0), 2)
    store_fee = round(float(purchase.store_fee or 0.0), 2)

    # 1) Reverse revenue — ACCRECCREDIT (credit note against the store customer),
    #    reduces income booked to 4010.
    rev_credit = _xero_post('CreditNotes', token, {'CreditNotes': [{
        'Type': 'ACCRECCREDIT',
        'Contact': {'ContactID': contact_id},
        'Date': date_str,
        'Reference': f"Refund-Rev-{purchase.platform}-{purchase.id}",
        'Status': 'AUTHORISED',
        'CurrencyCode': 'USD',
        'LineItems': [{
            'Description': f'{store_label} refund reversal — txn {purchase.transaction_id} ({period_key})',
            'Quantity': 1,
            'UnitAmount': price,
            'AccountCode': REVENUE_ACCOUNT_CODE,
            'TaxType': 'NONE',
        }],
    }]})
    if rev_credit.status_code != 200:
        err = rev_credit.text[:300]
        db.session.add(XeroSyncLog(
            sync_type='subscription_refund', entity_id=entity_id, entity_type='refund',
            amount=price, status='failed', error_message=err))
        db.session.commit()
        return {'error': f'revenue_credit_failed: {err}', 'purchase_id': purchase.id}
    rev_credit_id = rev_credit.json().get('CreditNotes', [{}])[0].get('CreditNoteID')

    # 2) Reverse store fee — ACCPAYCREDIT (the store returns its commission on a
    #    refund), reduces expense booked to 6100.
    fee_credit_id = None
    if store_fee > 0:
        fee_credit = _xero_post('CreditNotes', token, {'CreditNotes': [{
            'Type': 'ACCPAYCREDIT',
            'Contact': {'ContactID': contact_id},
            'Date': date_str,
            'Reference': f"Refund-Fee-{purchase.platform}-{purchase.id}",
            'Status': 'AUTHORISED',
            'CurrencyCode': 'USD',
            'LineItems': [{
                'Description': f'{store_label} commission reversal — txn {purchase.transaction_id} ({period_key})',
                'Quantity': 1,
                'UnitAmount': store_fee,
                'AccountCode': STORE_FEE_ACCOUNT_CODE,
                'TaxType': 'NONE',
            }],
        }]})
        if fee_credit.status_code == 200:
            fee_credit_id = fee_credit.json().get('CreditNotes', [{}])[0].get('CreditNoteID')
        else:
            logger.error(f"Store-fee credit note failed for purchase {purchase.id}: {fee_credit.text[:300]}")

    db.session.add(XeroSyncLog(
        sync_type='subscription_refund', entity_id=entity_id, entity_type='refund',
        xero_invoice_id=rev_credit_id, xero_contact_id=contact_id, amount=price, status='success'))
    db.session.commit()

    logger.info(f"Reversed refunded purchase {purchase.id}: -${price:.2f} revenue, "
                f"-${store_fee:.2f} store fee ({purchase.platform} {period_key})")
    return {'reversed': True, 'purchase_id': purchase.id, 'revenue_reversed': price,
            'store_fee_reversed': store_fee, 'revenue_credit_note_id': rev_credit_id,
            'store_fee_credit_note_id': fee_credit_id}


def reverse_refunded_purchases(period_start=None, period_end=None):
    """Sweep: reverse every refunded purchase whose revenue was already posted
    and that hasn't been reversed yet. Idempotent (per-purchase guard).

    Optional date filter narrows by purchase_date; default scans all refunds.
    """
    from models import db, InAppPurchase

    token = get_valid_token()
    if not token:
        return {'error': 'No valid Xero token — connect at /api/mobile/admin/xero/connect first'}

    q = InAppPurchase.query.filter(InAppPurchase.status == 'refunded')
    if period_start:
        q = q.filter(InAppPurchase.purchase_date >= datetime.combine(period_start, datetime.min.time()))
    if period_end:
        q = q.filter(InAppPurchase.purchase_date <= datetime.combine(period_end, datetime.max.time()))

    out = {'reversed': [], 'skipped': 0, 'failed': [], 'total_revenue_reversed': 0.0}
    for p in q.all():
        res = reverse_refunded_purchase(p, token=token)
        if res.get('reversed'):
            out['reversed'].append({'purchase_id': p.id, 'revenue': res['revenue_reversed'],
                                    'store_fee': res['store_fee_reversed']})
            out['total_revenue_reversed'] += res['revenue_reversed']
        elif res.get('error'):
            out['failed'].append({'purchase_id': p.id, 'error': res['error']})
        else:
            out['skipped'] += 1
    out['total_revenue_reversed'] = round(out['total_revenue_reversed'], 2)
    return out
