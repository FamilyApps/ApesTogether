"""App-level (column) encryption for sensitive PII at rest.

Fast-follow to the DB provider's disk-at-rest encryption: encrypts selected W-9
identity/address columns so a leaked DB dump or over-broad DB access does NOT
expose plaintext PII. The full TIN is never stored locally (it lives in Xero);
this protects the remaining identity fields (legal name, address, TIN last-4).

Opt-in and backward compatible:
  * If TAX_ENCRYPTION_KEY is not set, values pass through as plaintext (no
    behavior change) — so enabling encryption is a deploy-time decision.
  * On read, values that fail to decrypt (legacy plaintext, or a rotated key)
    are returned as-is, so turning encryption on does not break pre-existing
    rows written before the key existed.

IMPORTANT: ciphertext is longer than plaintext, so the encrypted columns are
stored as TEXT. Run scripts/migrations/2026_07_01_encrypt_taxpayer_pii.sql to
widen the columns BEFORE setting TAX_ENCRYPTION_KEY in an environment that has
existing data.

Generate a key once and store it in the environment (never in git):
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os
import logging
from sqlalchemy.types import TypeDecorator, Text

logger = logging.getLogger(__name__)

_FERNET = None
_INITIALIZED = False


def _get_fernet():
    """Lazily build the Fernet instance from TAX_ENCRYPTION_KEY (or None)."""
    global _FERNET, _INITIALIZED
    if not _INITIALIZED:
        _INITIALIZED = True
        key = os.environ.get('TAX_ENCRYPTION_KEY')
        if key:
            try:
                from cryptography.fernet import Fernet
                _FERNET = Fernet(key.encode() if isinstance(key, str) else key)
            except Exception as e:  # pragma: no cover - config error
                logger.error(f"TAX_ENCRYPTION_KEY invalid; storing plaintext: {e}")
                _FERNET = None
    return _FERNET


class EncryptedString(TypeDecorator):
    """Transparently Fernet-encrypts a string column at rest.

    Underlying storage is TEXT. No-ops to plaintext when no key is configured;
    tolerates legacy plaintext on read.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        f = _get_fernet()
        if f is None:
            return value  # no key -> plaintext passthrough
        try:
            return f.encrypt(str(value).encode('utf-8')).decode('ascii')
        except Exception as e:  # pragma: no cover
            logger.error(f"EncryptedString encrypt failed: {e}")
            return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        f = _get_fernet()
        if f is None:
            return value
        try:
            return f.decrypt(value.encode('ascii')).decode('utf-8')
        except Exception:
            # Legacy plaintext (written before the key existed) or a wrong/rotated
            # key. Return as-is so reads never hard-fail.
            return value
