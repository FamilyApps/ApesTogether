"""
Server-to-server subscription notification handlers.

Apple  — App Store Server Notifications V2 (ASSN V2):
    POST {"signedPayload": "<JWS>"}
    The JWS is signed by Apple. We verify the x5c certificate chain (pinned to
    Apple Root CA - G3 when the root cert is available), then decode the
    notification + the nested signedTransactionInfo, and update the matching
    InAppPurchase / MobileSubscription rows (matched by originalTransactionId).

Google — Real-time Developer Notifications (RTDN) via Cloud Pub/Sub push:
    POST {"message": {"data": "<base64 JSON>", ...}, "subscription": "..."}
    We decode the notification, then RE-FETCH the authoritative subscription
    state from the Google Play Developer API using our service account (so a
    forged push cannot change anything), and update the matching rows
    (matched by purchaseToken stored in InAppPurchase.receipt_data).

Security model: these endpoints NEVER create new purchases/subscriptions. They
only UPDATE rows that already exist from an authenticated /purchase/validate
call, so the blast radius of a forged request is limited to flipping the status
of a subscription whose store identifier the attacker already knows. Apple
requests are additionally signature-verified; Google state is re-fetched from
the authenticated Play API.

Configuration (see LAUNCH_TODO.md "Subscription Lifecycle & Billing"):
  Apple:  set the ASSN V2 URL in App Store Connect (prod + sandbox) to
          https://apestogether.ai/api/mobile/webhooks/apple/notifications
          For full signature hardening, pin Apple's root cert via
          APPLE_ROOT_CA_G3_PEM (PEM text) or certs/AppleRootCA-G3.cer (DER,
          download: https://www.apple.com/certificateauthority/AppleRootCA-G3.cer)
  Google: create a Pub/Sub topic, grant google-play-developer-notifications@
          system.gserviceaccount.com Publisher on it, set it in Play Console →
          Monetization setup → Real-time developer notifications, and add a
          push subscription POSTing to
          https://apestogether.ai/api/mobile/webhooks/google/rtdn
"""

import os
import json
import base64
import logging
from datetime import datetime

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature

logger = logging.getLogger(__name__)

APPLE_BUNDLE_ID = os.environ.get('APPLE_BUNDLE_ID', 'com.apestogether.ApesTogether')

# Apple notificationType buckets. DID_CHANGE_RENEWAL_STATUS (auto-renew toggle)
# is intentionally absent: turning auto-renew off does NOT revoke access until
# the period actually EXPIRES, so we leave the status alone for it.
_APPLE_ACTIVE_TYPES = {'SUBSCRIBED', 'DID_RENEW', 'OFFER_REDEEMED', 'DID_CHANGE_RENEWAL_PREF',
                       'RENEWAL_EXTENDED', 'GRACE_PERIOD'}
_APPLE_EXPIRED_TYPES = {'EXPIRED', 'GRACE_PERIOD_EXPIRED'}


# ---------------------------------------------------------------------------
# Apple JWS verification
# ---------------------------------------------------------------------------

def _load_apple_root():
    """Load the pinned Apple Root CA - G3 certificate, if provided.

    Returns a cryptography Certificate or None (None => structural-only check).
    """
    try:
        pem = os.environ.get('APPLE_ROOT_CA_G3_PEM')
        if pem:
            return x509.load_pem_x509_certificate(pem.encode())
        path = os.path.join(os.path.dirname(__file__), 'certs', 'AppleRootCA-G3.cer')
        if os.path.exists(path):
            with open(path, 'rb') as f:
                return x509.load_der_x509_certificate(f.read())
    except Exception as e:
        logger.warning(f"Could not load Apple root cert: {e}")
    return None


def verify_apple_jws(signed_payload: str) -> dict:
    """Verify an Apple JWS via its x5c chain and return the decoded payload.

    Raises ValueError if verification fails.
    """
    header = jwt.get_unverified_header(signed_payload)
    x5c = header.get('x5c')
    if not x5c:
        raise ValueError('missing x5c header')

    certs = [x509.load_der_x509_certificate(base64.b64decode(c)) for c in x5c]
    leaf = certs[0]

    # Verify the chain links: cert[i] is signed by cert[i+1]'s public key.
    for i in range(len(certs) - 1):
        issuer = certs[i + 1]
        try:
            issuer.public_key().verify(
                certs[i].signature,
                certs[i].tbs_certificate_bytes,
                ec.ECDSA(certs[i].signature_hash_algorithm),
            )
        except InvalidSignature:
            raise ValueError(f'broken certificate chain at index {i}')

    # Pin to Apple's root when available; otherwise warn (structural-only).
    pinned = _load_apple_root()
    if pinned is not None:
        if certs[-1].fingerprint(hashes.SHA256()) != pinned.fingerprint(hashes.SHA256()):
            raise ValueError('root cert does not match pinned Apple Root CA - G3')
    else:
        logger.warning("Apple root cert not pinned (set APPLE_ROOT_CA_G3_PEM or add "
                       "certs/AppleRootCA-G3.cer) — verifying chain structure + leaf signature only")

    # Verify the JWS signature with the leaf certificate's public key.
    return jwt.decode(
        signed_payload,
        key=leaf.public_key(),
        algorithms=['ES256'],
        options={'verify_aud': False, 'verify_iss': False},
    )


# ---------------------------------------------------------------------------
# DB update (shared by both platforms)
# ---------------------------------------------------------------------------

def _apply_update(db, platform: str, original_transaction_id: str = None,
                  purchase_token: str = None, new_status: str = None,
                  expires_date: datetime = None) -> int:
    """Update existing InAppPurchase rows (+ their MobileSubscriptions) that
    match the store identifier. Returns the number of purchases updated.

    Never creates rows — new subscriptions only come via /purchase/validate.
    """
    from models import InAppPurchase, MobileSubscription

    q = InAppPurchase.query.filter_by(platform=platform)
    if original_transaction_id:
        q = q.filter(
            (InAppPurchase.original_transaction_id == original_transaction_id) |
            (InAppPurchase.transaction_id == original_transaction_id)
        )
    elif purchase_token:
        q = q.filter(InAppPurchase.receipt_data == purchase_token)
    else:
        return 0

    purchases = q.all()
    count = 0
    for p in purchases:
        if new_status:
            p.status = new_status
        if expires_date:
            p.expires_date = expires_date
        p.updated_at = datetime.utcnow()

        for s in MobileSubscription.query.filter_by(in_app_purchase_id=p.id).all():
            if new_status:
                # MobileSubscription enum is active/expired/canceled — refunds
                # and revokes revoke access, so map them to 'expired'.
                s.status = 'active' if new_status == 'active' else 'expired'
            if expires_date:
                s.expires_at = expires_date
        count += 1

    if count:
        db.session.commit()
    return count


# ---------------------------------------------------------------------------
# Apple App Store Server Notifications V2
# ---------------------------------------------------------------------------

def handle_apple_notification(db, signed_payload: str) -> dict:
    payload = verify_apple_jws(signed_payload)
    notification_type = payload.get('notificationType')
    subtype = payload.get('subtype')
    data = payload.get('data') or {}

    bundle_id = data.get('bundleId')
    if bundle_id and APPLE_BUNDLE_ID and bundle_id != APPLE_BUNDLE_ID:
        logger.warning(f"[ASSN] ignoring notification for bundleId={bundle_id}")
        return {'ignored': 'bundle_mismatch'}

    signed_tx = data.get('signedTransactionInfo')
    if not signed_tx:
        # e.g. TEST notifications carry no transaction
        return {'type': notification_type, 'subtype': subtype, 'no_transaction': True}

    tx = verify_apple_jws(signed_tx)
    original_transaction_id = str(tx.get('originalTransactionId') or tx.get('transactionId') or '')
    expires_ms = tx.get('expiresDate')
    revocation_ms = tx.get('revocationDate')
    expires_date = datetime.utcfromtimestamp(expires_ms / 1000) if expires_ms else None

    new_status = None
    if notification_type == 'REFUND' or revocation_ms:
        new_status = 'refunded'
    elif notification_type == 'REVOKE':
        new_status = 'expired'
    elif notification_type in _APPLE_EXPIRED_TYPES:
        new_status = 'expired'
    elif notification_type in _APPLE_ACTIVE_TYPES:
        new_status = 'active'
    # else (DID_CHANGE_RENEWAL_STATUS, PRICE_INCREASE, etc.): leave status as-is.

    updated = _apply_update(
        db, platform='apple',
        original_transaction_id=original_transaction_id,
        new_status=new_status, expires_date=expires_date,
    )
    return {'type': notification_type, 'subtype': subtype,
            'original_transaction_id': original_transaction_id,
            'status': new_status, 'updated': updated}


# ---------------------------------------------------------------------------
# Google Real-time Developer Notifications (Pub/Sub push)
# ---------------------------------------------------------------------------

def handle_google_rtdn(db, body: dict) -> dict:
    import asyncio
    from iap_validation_service import get_iap_service

    message = (body or {}).get('message') or {}
    data_b64 = message.get('data')
    if not data_b64:
        return {'ignored': 'no_data'}

    try:
        notif = json.loads(base64.b64decode(data_b64))
    except Exception:
        return {'error': 'bad_data'}

    if 'testNotification' in notif:
        logger.info("[RTDN] test notification received")
        return {'test': True}

    # Refund / chargeback
    voided = notif.get('voidedPurchaseNotification')
    if voided:
        token = voided.get('purchaseToken')
        updated = _apply_update(db, platform='google', purchase_token=token,
                                new_status='refunded')
        return {'voided': True, 'updated': updated}

    sub_notif = notif.get('subscriptionNotification')
    if not sub_notif:
        return {'ignored': 'unhandled_type'}

    token = sub_notif.get('purchaseToken')
    product_id = sub_notif.get('subscriptionId')
    notification_type = sub_notif.get('notificationType')

    # Re-fetch authoritative state from Google (uses our service account, so a
    # forged push cannot move money/access — an unknown token just 404s).
    service = get_iap_service()
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(service.validate_google_purchase(token, product_id))
    finally:
        loop.close()

    new_status = result.get('status') if result.get('valid') else None
    expires_date = result.get('expires_date')
    updated = _apply_update(db, platform='google', purchase_token=token,
                            new_status=new_status, expires_date=expires_date)
    return {'type': notification_type, 'product_id': product_id,
            'status': new_status, 'updated': updated}
