"""
Tests for apple_jws_verifier using a SYNTHETIC certificate chain.

We can't ship a real Apple-signed JWS, so we build our own root ->
intermediate -> leaf chain (same shapes/algorithms Apple uses: ES256 / P-256),
sign a JWS with the leaf, and assert the verifier:
  * accepts an authentic JWS whose chain terminates at the pinned root,
  * rejects a tampered payload (bad signature),
  * rejects a chain that terminates at an untrusted root,
  * rejects a broken chain (leaf not signed by the presented intermediate),
  * reports ROOT_NOT_CONFIGURED when the trust anchor file is absent.

Run directly:  python tests/test_apple_jws_verifier.py
"""

import base64
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

import jwt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import apple_jws_verifier as v


def _key():
    return ec.generate_private_key(ec.SECP256R1())


def _cert(cn, subject_key, issuer_key, issuer_cn=None, ca=True):
    issuer_cn = issuer_cn or cn
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)]))
        .public_key(subject_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    return builder.sign(private_key=issuer_key, algorithm=hashes.SHA256())


def _der_b64(cert):
    return base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()


def _make_jws(payload, leaf_key, x5c_certs):
    return jwt.encode(payload, key=leaf_key, algorithm='ES256',
                      headers={'x5c': [_der_b64(c) for c in x5c_certs]})


def _write_root(cert):
    f = tempfile.NamedTemporaryFile(suffix='.cer', delete=False)
    f.write(cert.public_bytes(serialization.Encoding.DER))
    f.close()
    os.environ['APPLE_ROOT_CA_PATH'] = f.name
    v.reset_root_cache()
    return f.name


def build_chain():
    root_key, int_key, leaf_key = _key(), _key(), _key()
    root = _cert('Test Apple Root CA - G3', root_key, root_key)
    intermediate = _cert('Test Apple WWDR', int_key, root_key, issuer_cn='Test Apple Root CA - G3')
    leaf = _cert('Test Apple Leaf', leaf_key, int_key, issuer_cn='Test Apple WWDR', ca=False)
    return root_key, int_key, leaf_key, root, intermediate, leaf


PAYLOAD = {'productId': 'com.apestogether.sub.s02.annual', 'transactionId': '123',
           'bundleId': 'com.apestogether.ApesTogether', 'environment': 'Sandbox'}


def test_accepts_authentic_jws():
    _, _, leaf_key, root, intermediate, leaf = build_chain()
    _write_root(root)
    jws = _make_jws(PAYLOAD, leaf_key, [leaf, intermediate, root])
    out = v.verify_and_decode(jws)
    assert out['productId'] == 'com.apestogether.sub.s02.annual', out
    print('PASS authentic JWS accepted')


def test_rejects_tampered_payload():
    _, _, leaf_key, root, intermediate, leaf = build_chain()
    _write_root(root)
    jws = _make_jws(PAYLOAD, leaf_key, [leaf, intermediate, root])
    h, p, s = jws.split('.')
    forged = {'productId': 'com.apestogether.sub.s20.annual', 'transactionId': '999',
              'bundleId': 'com.apestogether.ApesTogether'}
    p2 = base64.urlsafe_b64encode(json.dumps(forged).encode()).decode().rstrip('=')
    tampered = f'{h}.{p2}.{s}'
    try:
        v.verify_and_decode(tampered)
        assert False, 'tampered payload was accepted!'
    except v.AppleJWSVerificationError as e:
        assert 'signature' in str(e), e
        print('PASS tampered payload rejected:', e)


def test_rejects_untrusted_root():
    _, _, leaf_key, root, intermediate, leaf = build_chain()
    other_root_key = _key()
    other_root = _cert('Attacker Root', other_root_key, other_root_key)
    _write_root(other_root)  # pin a DIFFERENT root than the chain terminates at
    jws = _make_jws(PAYLOAD, leaf_key, [leaf, intermediate, root])
    try:
        v.verify_and_decode(jws)
        assert False, 'untrusted root was accepted!'
    except v.AppleJWSVerificationError as e:
        assert str(e) == 'untrusted_root', e
        print('PASS untrusted root rejected:', e)


def test_rejects_broken_chain():
    root_key, _, leaf_key, root, intermediate, leaf = build_chain()
    # A different intermediate, also signed by the real root, but which did NOT
    # sign the leaf. Presenting it should break leaf<-intermediate verification.
    fake_int_key = _key()
    fake_int = _cert('Fake WWDR', fake_int_key, root_key, issuer_cn='Test Apple Root CA - G3')
    _write_root(root)
    jws = _make_jws(PAYLOAD, leaf_key, [leaf, fake_int, root])
    try:
        v.verify_and_decode(jws)
        assert False, 'broken chain was accepted!'
    except v.AppleJWSVerificationError as e:
        assert str(e) == 'broken_certificate_chain', e
        print('PASS broken chain rejected:', e)


def test_reports_not_configured_when_missing():
    os.environ['APPLE_ROOT_CA_PATH'] = os.path.join(tempfile.gettempdir(), 'nope-missing.cer')
    v.reset_root_cache()
    try:
        v.verify_and_decode('a.b.c')
        assert False, 'should have raised'
    except v.AppleJWSVerificationError as e:
        assert str(e) == v.ROOT_NOT_CONFIGURED, e
        print('PASS reports not-configured when root absent:', e)


def test_integration_with_iap_service():
    """End-to-end: a verified slot-ANNUAL JWS through IAPValidationService must
    come back valid, with the slot derived and ANNUAL pricing applied."""
    import time
    import types
    sys.modules.setdefault('httpx', types.ModuleType('httpx'))  # avoid prod dep
    _, _, leaf_key, root, intermediate, leaf = build_chain()
    _write_root(root)
    os.environ['APPLE_BUNDLE_ID'] = 'com.apestogether.ApesTogether'
    import iap_validation_service
    svc = iap_validation_service.IAPValidationService()

    now_ms = int(time.time() * 1000)
    payload = {'productId': 'com.apestogether.sub.s02.annual', 'transactionId': 'tx1',
               'originalTransactionId': 'tx1', 'bundleId': 'com.apestogether.ApesTogether',
               'environment': 'Sandbox', 'purchaseDate': now_ms,
               'expiresDate': now_ms + 31_536_000_000}
    jws = _make_jws(payload, leaf_key, [leaf, intermediate, root])

    res = svc._parse_storekit2_jws(jws)
    assert res['valid'] is True, res
    assert res['product_id'] == 'com.apestogether.sub.s02.annual', res
    assert res['price'] == 69.00 and res['billing_period'] == 'annual', res
    print('PASS integration: verified slot-annual JWS -> price', res['price'], res['billing_period'])

    svc.apple_bundle_id = 'com.attacker.app'
    res2 = svc._parse_storekit2_jws(jws)
    assert res2['valid'] is False and res2['error'] == 'bundle_id_mismatch', res2
    print('PASS integration: bundleId mismatch rejected')


def main():
    test_accepts_authentic_jws()
    test_rejects_tampered_payload()
    test_rejects_untrusted_root()
    test_rejects_broken_chain()
    test_reports_not_configured_when_missing()
    test_integration_with_iap_service()
    print('\nALL APPLE JWS VERIFIER TESTS PASSED')


if __name__ == '__main__':
    main()
