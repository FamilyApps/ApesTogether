# Trust anchors

## AppleRootCA-G3.cer  (required to verify StoreKit 2 purchases)

`apple_jws_verifier.py` verifies every StoreKit 2 signed transaction against
**Apple Root CA - G3**. Until this file exists, the backend falls back to
decode-only (insecure) and logs a CRITICAL warning on every Apple purchase.

Download the official cert (public, safe to commit) into this folder:

```powershell
Invoke-WebRequest -Uri "https://www.apple.com/certificateauthority/AppleRootCA-G3.cer" -OutFile "certs\AppleRootCA-G3.cer"
```

```bash
curl -o certs/AppleRootCA-G3.cer https://www.apple.com/certificateauthority/AppleRootCA-G3.cer
```

Then commit it and redeploy. Override the path with `APPLE_ROOT_CA_PATH` if needed.
DER or PEM are both accepted.
