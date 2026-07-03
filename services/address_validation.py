"""USPS Addresses 3.0 — free U.S. address validation / standardization.

Validates and standardizes a U.S. address via the official USPS APIs
(https://developer.usps.com). US-only, which is exactly what a W-9 needs
(W-9 = U.S. persons). Requires OAuth2 client-credentials from the USPS
Developer Portal, supplied via environment variables:

    USPS_CLIENT_ID       (consumer key from your USPS app)
    USPS_CLIENT_SECRET   (consumer secret)
    USPS_API_BASE        (optional; defaults to prod https://apis.usps.com,
                          use https://apis-tem.usps.com for the test env)

Design principle — FAIL-OPEN: if credentials are missing, the network call
fails, or the response is ambiguous, we return status='unavailable' and the
caller should ALLOW the submission (format + state + ZIP regex are already
enforced upstream). We only report 'undeliverable' when USPS definitively says
the address is not a valid delivery point, so a real creator is never blocked
by an API hiccup.
"""
import os
import time
import logging

import requests

logger = logging.getLogger(__name__)

# Cached OAuth token (module-level; resets on deploy). {'value', 'expires_at'}
_TOKEN = {'value': None, 'expires_at': 0.0}
_TOKEN_SKEW = 60  # refresh a minute before expiry


def is_configured():
    """True if USPS OAuth credentials are present in the environment."""
    return bool(os.environ.get('USPS_CLIENT_ID') and os.environ.get('USPS_CLIENT_SECRET'))


def _base():
    return os.environ.get('USPS_API_BASE', 'https://apis.usps.com').rstrip('/')


def _get_token(timeout=8):
    """Return a valid Bearer token, or None if unavailable. Caches until expiry."""
    now = time.time()
    if _TOKEN['value'] and now < _TOKEN['expires_at']:
        return _TOKEN['value']

    client_id = os.environ.get('USPS_CLIENT_ID')
    client_secret = os.environ.get('USPS_CLIENT_SECRET')
    if not (client_id and client_secret):
        return None

    resp = requests.post(
        f'{_base()}/oauth2/v3/token',
        json={
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'client_credentials',
        },
        headers={'Content-Type': 'application/json'},
        timeout=timeout,
    )
    resp.raise_for_status()
    tok = resp.json()
    _TOKEN['value'] = tok['access_token']
    # expires_in comes back as a string (e.g. "3599"); coerce defensively.
    try:
        ttl = int(tok.get('expires_in', 3600))
    except (TypeError, ValueError):
        ttl = 3600
    _TOKEN['expires_at'] = now + ttl - _TOKEN_SKEW
    return _TOKEN['value']


def validate_us_address(street, city, state, zip5, secondary=None, timeout=8):
    """Validate / standardize a U.S. address via USPS Addresses 3.0.

    Returns a dict:
        {
          'status': 'deliverable' | 'undeliverable' | 'unavailable',
          'standardized': {line1, line2, city, state, postal_code, zip4} | None,
          'message': str,
        }

    'unavailable' means we couldn't get a definitive answer (not configured,
    network error, rate limit, etc.) — callers should FAIL-OPEN and allow.
    """
    if not is_configured():
        return {'status': 'unavailable', 'standardized': None, 'message': 'not_configured'}

    try:
        token = _get_token(timeout=timeout)
        if not token:
            return {'status': 'unavailable', 'standardized': None, 'message': 'no_token'}

        params = {'streetAddress': street, 'city': city, 'state': state}
        if zip5:
            params['ZIPCode'] = str(zip5)[:5]
        if secondary:
            params['secondaryAddress'] = secondary

        resp = requests.get(
            f'{_base()}/addresses/v3/address',
            params=params,
            headers={'Authorization': f'Bearer {token}', 'accept': 'application/json'},
            timeout=timeout,
        )

        # USPS returns 400/404 when it can't match the address at all.
        if resp.status_code in (400, 404):
            return {'status': 'undeliverable', 'standardized': None,
                    'message': 'USPS could not find this address.'}
        resp.raise_for_status()

        body = resp.json() or {}
        addr = body.get('address') or {}
        info = body.get('additionalInfo') or {}
        dpv = (info.get('DPVConfirmation') or '').upper()

        standardized = {
            'line1': addr.get('streetAddress'),
            'line2': addr.get('secondaryAddress'),
            'city': addr.get('city'),
            'state': addr.get('state'),
            'postal_code': addr.get('ZIPCode'),
            'zip4': addr.get('ZIPPlus4'),
        }

        # DPVConfirmation: Y = confirmed deliverable delivery point;
        # D/S = primary address ok but secondary (apt/suite) missing or wrong;
        # N or empty = not a confirmed delivery point.
        if dpv == 'Y':
            return {'status': 'deliverable', 'standardized': standardized,
                    'message': 'USPS confirmed this address.'}
        if dpv in ('D', 'S'):
            return {'status': 'deliverable', 'standardized': standardized,
                    'message': 'USPS confirmed the street address; verify the apartment/suite.'}
        if not addr.get('streetAddress'):
            return {'status': 'undeliverable', 'standardized': None,
                    'message': 'USPS could not find this address.'}
        return {'status': 'undeliverable', 'standardized': standardized,
                'message': 'USPS could not confirm this address is deliverable.'}

    except Exception as e:
        logger.warning(f'[usps] address validation unavailable: {e}')
        return {'status': 'unavailable', 'standardized': None, 'message': 'lookup_error'}
