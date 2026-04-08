"""
W-9 encryption and validation service.

Handles:
- Fernet symmetric encryption/decryption of TIN (SSN/EIN)
- W-9 form validation
- Payout hold logic

ENCRYPTION_KEY env var must be a Fernet key (generated via: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
"""
import os
import re
import logging
from datetime import date

logger = logging.getLogger(__name__)

# Lazy-load cryptography to avoid import errors if not installed
_fernet = None

def _get_fernet():
    """Get or create Fernet cipher from ENCRYPTION_KEY env var."""
    global _fernet
    if _fernet is not None:
        return _fernet
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.error("cryptography package not installed. Run: pip install cryptography")
        return None
    key = os.environ.get('ENCRYPTION_KEY')
    if not key:
        logger.error("ENCRYPTION_KEY env var not set. W-9 encryption disabled.")
        return None
    try:
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
        return _fernet
    except Exception as e:
        logger.error(f"Invalid ENCRYPTION_KEY: {e}")
        return None


def encrypt_tin(tin_plain: str) -> bytes:
    """Encrypt a TIN (SSN or EIN) using Fernet. Returns encrypted bytes."""
    f = _get_fernet()
    if not f:
        raise RuntimeError("Encryption not available — ENCRYPTION_KEY not configured")
    return f.encrypt(tin_plain.encode('utf-8'))


def decrypt_tin(tin_encrypted: bytes) -> str:
    """Decrypt a TIN. Returns plain text SSN/EIN."""
    f = _get_fernet()
    if not f:
        raise RuntimeError("Decryption not available — ENCRYPTION_KEY not configured")
    return f.decrypt(tin_encrypted).decode('utf-8')


# ── Validation helpers ────────────────────────────────────────────────────────

VALID_TAX_CLASSIFICATIONS = {
    'individual', 'sole_proprietor', 'llc_single', 'llc_partnership',
    'llc_c_corp', 'llc_s_corp', 'c_corp', 's_corp', 'partnership',
    'trust_estate', 'other'
}

US_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
    'DC', 'PR', 'VI', 'GU', 'AS', 'MP'
}


def validate_ssn(ssn: str) -> bool:
    """Validate SSN format: 9 digits, no all-zeros groups, no 9xx prefix (ITIN range)."""
    digits = re.sub(r'\D', '', ssn)
    if len(digits) != 9:
        return False
    area, group, serial = digits[:3], digits[3:5], digits[5:]
    if area == '000' or group == '00' or serial == '0000':
        return False
    if area == '666':
        return False
    return True


def validate_ein(ein: str) -> bool:
    """Validate EIN format: 9 digits, first 2 form a valid prefix."""
    digits = re.sub(r'\D', '', ein)
    if len(digits) != 9:
        return False
    prefix = int(digits[:2])
    # Valid EIN prefixes (IRS campus codes)
    valid_prefixes = set(range(1, 100)) - {7, 8, 9, 17, 18, 19, 28, 29, 49, 69, 70, 78, 79, 89}
    return prefix in valid_prefixes


def validate_zip(zip_code: str) -> bool:
    """Validate ZIP code: 5 digits or ZIP+4 (5-4)."""
    return bool(re.match(r'^\d{5}(-\d{4})?$', zip_code.strip()))


def validate_w9_data(data: dict) -> list:
    """
    Validate W-9 form data. Returns list of error strings (empty = valid).
    
    Required fields:
    - legal_first_name, legal_last_name
    - tax_classification
    - address_line1, city, state, zip_code
    - tin_type ('ssn' or 'ein'), tin (the actual number)
    - signature_name
    """
    errors = []
    
    # Name
    if not data.get('legal_first_name', '').strip():
        errors.append('Legal first name is required')
    if not data.get('legal_last_name', '').strip():
        errors.append('Legal last name is required')
    
    # Tax classification
    tc = data.get('tax_classification', '')
    if tc not in VALID_TAX_CLASSIFICATIONS:
        errors.append(f'Invalid tax classification: {tc}')
    
    # Address
    if not data.get('address_line1', '').strip():
        errors.append('Street address is required')
    if not data.get('city', '').strip():
        errors.append('City is required')
    state = data.get('state', '').upper().strip()
    if state not in US_STATES:
        errors.append(f'Invalid state: {state}')
    if not validate_zip(data.get('zip_code', '')):
        errors.append('Invalid ZIP code (use 12345 or 12345-6789)')
    
    # TIN
    tin_type = data.get('tin_type', '')
    tin = data.get('tin', '')
    if tin_type == 'ssn':
        if not validate_ssn(tin):
            errors.append('Invalid SSN format')
    elif tin_type == 'ein':
        if not validate_ein(tin):
            errors.append('Invalid EIN format')
    else:
        errors.append('tin_type must be "ssn" or "ein"')
    
    # Signature
    if not data.get('signature_name', '').strip():
        errors.append('Signature (typed legal name) is required')
    
    return errors


# ── Payout hold logic ─────────────────────────────────────────────────────────

def user_has_valid_w9(user_id: int) -> bool:
    """Check if a user has an active (submitted or verified) W-9 on file."""
    from models import W9Submission
    return W9Submission.query.filter_by(user_id=user_id).filter(
        W9Submission.status.in_(['submitted', 'verified'])
    ).first() is not None


def get_w9_status(user_id: int) -> dict:
    """Get W-9 status for a user. Returns dict with status details."""
    from models import W9Submission
    latest = W9Submission.query.filter_by(user_id=user_id).order_by(
        W9Submission.created_at.desc()
    ).first()
    
    if not latest:
        return {
            'has_w9': False,
            'status': 'not_submitted',
            'message': 'W-9 form not yet submitted. Required before payouts can be processed.'
        }
    
    return {
        'has_w9': latest.is_active,
        'status': latest.status,
        'submitted_at': latest.created_at.isoformat() if latest.created_at else None,
        'reviewed_at': latest.reviewed_at.isoformat() if latest.reviewed_at else None,
        'rejection_reason': latest.rejection_reason if latest.status == 'rejected' else None,
        'tin_display': latest.display_tin,
        'legal_name': f"{latest.legal_first_name} {latest.legal_last_name}",
        'message': {
            'submitted': 'W-9 submitted. Under review.',
            'verified': 'W-9 verified. Payouts enabled.',
            'rejected': f'W-9 rejected: {latest.rejection_reason}. Please resubmit.',
            'superseded': 'This W-9 has been replaced by a newer submission.',
        }.get(latest.status, 'Unknown status')
    }
