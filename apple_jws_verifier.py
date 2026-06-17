"""
Verify Apple StoreKit 2 / App Store Server signed JWS transactions.

Apple signs every StoreKit 2 transaction as a JWS whose header carries the
signing certificate chain in the `x5c` field. A genuine transaction's chain is
  leaf  ->  Apple Worldwide Developer Relations (intermediate)  ->  Apple Root CA - G3
and the JWS body is signed (ES256) by the leaf's private key.

Decoding the payload WITHOUT verifying this chain + signature is insecure: any
client could forge a JWS and mint a paid subscription for free. This module
performs full verification:

  1. Parse the x5c chain (leaf first).
  2. Verify each link is really signed by the next (leaf<-intermediate<-root).
  3. Pin trust: the chain's terminal cert must be exactly the Apple Root CA - G3
     certificate we ship (compared by SHA-256 fingerprint).
  4. Verify the JWS ES256 signature with the leaf certificate's public key.
  5. Return the decoded payload only if all checks pass; otherwise raise.

TRUST ANCHOR (one-time setup): download Apple Root CA - G3 (DER) from
https://www.apple.com/certificateauthority/AppleRootCA-G3.cer and commit it to
certs/AppleRootCA-G3.cer (or point APPLE_ROOT_CA_PATH at it). Until the file is
present the caller falls back to decode-only (see iap_validation_service).
"""

import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.exceptions import InvalidSignature

import jwt  # PyJWT — used only to verify the leaf ES256 signature (handles r||s)

logger = logging.getLogger(__name__)

_DEFAULT_ROOT_PATH = os.path.join(os.path.dirname(__file__), 'certs', 'AppleRootCA-G3.cer')


class AppleJWSVerificationError(Exception):
    """Raised when a StoreKit 2 JWS fails cryptographic verification."""


# Special-case sentinel so the caller can distinguish "not set up yet" (safe to
# fall back) from "actively failed verification" (must reject).
ROOT_NOT_CONFIGURED = 'apple_root_ca_not_configured'


def _b64url_decode(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + '=' * (-len(seg) % 4))


def _load_cert(data: bytes) -> x509.Certificate:
    try:
        return x509.load_der_x509_certificate(data)
    except ValueError:
        return x509.load_pem_x509_certificate(data)


_root_cert = None
_root_loaded = False


def _load_root_cert() -> Optional[x509.Certificate]:
    """Load and cache the pinned Apple Root CA - G3 cert, or None if missing."""
    global _root_cert, _root_loaded
    if _root_loaded:
        return _root_cert
    _root_loaded = True
    path = os.environ.get('APPLE_ROOT_CA_PATH', _DEFAULT_ROOT_PATH)
    try:
        with open(path, 'rb') as f:
            _root_cert = _load_cert(f.read())
        logger.info("Apple Root CA loaded for JWS verification: %s", path)
    except FileNotFoundError:
        _root_cert = None
    except Exception as e:
        logger.error("Failed to load Apple Root CA from %s: %s", path, e)
        _root_cert = None
    return _root_cert


def reset_root_cache():
    """Test helper — clear the cached root so a new APPLE_ROOT_CA_PATH is read."""
    global _root_cert, _root_loaded
    _root_cert = None
    _root_loaded = False


def is_configured() -> bool:
    return _load_root_cert() is not None


def _verify_cert_signed_by(child: x509.Certificate, parent: x509.Certificate):
    pub = parent.public_key()
    if isinstance(pub, ec.EllipticCurvePublicKey):
        pub.verify(child.signature, child.tbs_certificate_bytes,
                   ec.ECDSA(child.signature_hash_algorithm))
    elif isinstance(pub, rsa.RSAPublicKey):
        pub.verify(child.signature, child.tbs_certificate_bytes,
                   padding.PKCS1v15(), child.signature_hash_algorithm)
    else:
        raise AppleJWSVerificationError('unsupported_parent_key_type')


def verify_and_decode(jws: str) -> dict:
    """Verify `jws` against Apple's pinned root and return its decoded payload.

    Raises AppleJWSVerificationError on any failure. The error message is
    ROOT_NOT_CONFIGURED when the trust anchor file is absent, which the caller
    treats as "not set up yet" rather than "forged".
    """
    root = _load_root_cert()
    if root is None:
        raise AppleJWSVerificationError(ROOT_NOT_CONFIGURED)

    parts = jws.split('.')
    if len(parts) != 3:
        raise AppleJWSVerificationError('invalid_jws_format')
    header_b64, payload_b64, _sig_b64 = parts

    try:
        header = json.loads(_b64url_decode(header_b64))
    except Exception:
        raise AppleJWSVerificationError('invalid_jws_header')

    x5c = header.get('x5c')
    if not x5c or len(x5c) < 2:
        raise AppleJWSVerificationError('missing_x5c_chain')

    try:
        # x5c entries are standard (not url-safe) base64-encoded DER certs.
        chain = [_load_cert(base64.b64decode(c)) for c in x5c]
    except Exception:
        raise AppleJWSVerificationError('invalid_x5c_certificate')
    leaf = chain[0]

    # 1) Pin: the chain must terminate at the Apple Root CA - G3 we ship.
    if chain[-1].fingerprint(hashes.SHA256()) != root.fingerprint(hashes.SHA256()):
        raise AppleJWSVerificationError('untrusted_root')

    # 2) Validity windows + each link is really signed by its parent.
    now = datetime.now(timezone.utc)
    for i, cert in enumerate(chain):
        if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
            raise AppleJWSVerificationError('certificate_expired_or_not_yet_valid')
        if i + 1 < len(chain):
            try:
                _verify_cert_signed_by(cert, chain[i + 1])
            except InvalidSignature:
                raise AppleJWSVerificationError('broken_certificate_chain')

    # 3) Verify the JWS signature with the leaf's public key (ES256).
    leaf_pub = leaf.public_key()
    if not isinstance(leaf_pub, ec.EllipticCurvePublicKey):
        raise AppleJWSVerificationError('unexpected_leaf_key_type')
    try:
        jwt.decode(jws, key=leaf_pub, algorithms=['ES256'],
                   options={'verify_signature': True, 'verify_exp': False,
                            'verify_aud': False, 'verify_iss': False,
                            'verify_nbf': False, 'verify_iat': False})
    except jwt.InvalidSignatureError:
        raise AppleJWSVerificationError('invalid_jws_signature')
    except jwt.InvalidAlgorithmError:
        raise AppleJWSVerificationError('unexpected_jws_algorithm')
    except jwt.PyJWTError as e:
        # Any other PyJWT complaint (we disabled claim checks above) is unexpected.
        raise AppleJWSVerificationError(f'jws_verify_error: {e}')

    # All checks passed — the payload is authentic.
    try:
        return json.loads(_b64url_decode(payload_b64))
    except Exception:
        raise AppleJWSVerificationError('invalid_jws_payload')
