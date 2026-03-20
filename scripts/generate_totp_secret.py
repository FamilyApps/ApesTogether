"""
Generate a TOTP secret for admin 2FA.
Run this once, save the secret as ADMIN_TOTP_SECRET env var in Vercel,
and scan the QR code with Google Authenticator / Authy.
"""
import base64
import os
import urllib.parse

# Generate a random 20-byte secret
secret_bytes = os.urandom(20)
secret_b32 = base64.b32encode(secret_bytes).decode('ascii')

# Generate otpauth:// URI for authenticator apps
issuer = 'ApesTogether'
account = 'admin@apestogether.ai'
otpauth_uri = (
    f"otpauth://totp/{urllib.parse.quote(issuer)}:{urllib.parse.quote(account)}"
    f"?secret={secret_b32}&issuer={urllib.parse.quote(issuer)}&algorithm=SHA1&digits=6&period=30"
)

print("=" * 60)
print("TOTP SECRET GENERATED")
print("=" * 60)
print()
print(f"Base32 Secret: {secret_b32}")
print()
print("Add to Vercel environment variables:")
print(f"  ADMIN_TOTP_SECRET = {secret_b32}")
print()
print("Scan this URI with Google Authenticator / Authy:")
print(f"  {otpauth_uri}")
print()
print("Or manually enter the secret in your authenticator app:")
print(f"  Account: {account}")
print(f"  Secret:  {secret_b32}")
print(f"  Type:    Time-based (TOTP)")
print(f"  Period:  30 seconds")
print(f"  Digits:  6")
print()
print("QR Code URL (paste in browser):")
qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(otpauth_uri)}"
print(f"  {qr_url}")
print()
print("IMPORTANT: Save the secret BEFORE closing this window!")
print("=" * 60)
