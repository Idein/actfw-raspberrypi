Public certificates for offline CA regression checks. No private keys are included.

Public sources:
- The six affected TLS intermediates: [Mozilla incident attachment](https://bugzilla.mozilla.org/attachment.cgi?id=9664067).
- Intermediate SHA-256 fingerprints: [Mozilla incident 2083449, comment 2](https://bugzilla.mozilla.org/show_bug.cgi?id=2083449#c2).
- The two root certificates: the Mozilla CA bundle distributed in [certifi 2025.1.31](https://pypi.org/project/certifi/2025.1.31/).
- Amazon Root CA 1, the positive control: [certifi 2026.10.19](https://pypi.org/project/certifi/2026.10.19/).

Tests use a fixed date and require issuer/self-signed errors rather than expiry errors.
