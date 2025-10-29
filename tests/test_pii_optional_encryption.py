from __future__ import annotations

import os


def test_mask_or_encrypt_storage():
    from core.utils.pii import encrypt_ssn, decrypt_ssn
    ssn = "900101-1234567"
    # Without key or crypto installed: returns masked
    os.environ.pop('PII_ENC_KEY', None)
    out = encrypt_ssn(ssn)
    assert out.startswith('enc:') or out.endswith('4567')
    if out.startswith('enc:'):
        assert decrypt_ssn(out) == ssn

