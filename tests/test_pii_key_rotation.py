from __future__ import annotations

import os
import pytest

cryptography = pytest.importorskip("cryptography")
from cryptography.fernet import Fernet  # type: ignore


def test_pii_key_rotation_encrypt_decrypt_sequence():
    from core.utils.pii import encrypt_ssn, decrypt_ssn
    ssn = "900101-1234567"
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    # Initial state: single key (old)
    os.environ['PII_ENC_KEYS'] = old_key
    enc1 = encrypt_ssn(ssn)
    assert enc1.startswith('enc:')
    assert decrypt_ssn(enc1) == ssn

    # Rotation in progress: both keys configured (new first)
    os.environ['PII_ENC_KEYS'] = f"{new_key},{old_key}"
    # Decrypt with new+old list should still work for old ciphertext
    assert decrypt_ssn(enc1) == ssn
    # New encryptions use the first (new) key
    enc2 = encrypt_ssn(ssn)
    assert enc2.startswith('enc:')
    assert enc2 != enc1
    assert decrypt_ssn(enc2) == ssn

