import hashlib
import os
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def generate_salt() -> bytes:
    return os.urandom(32)

def derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive AES-256 key from passphrase using PBKDF2 with SHA256."""
    return hashlib.pbkdf2_hmac('sha256', passphrase.encode('utf-8'), salt, 600_000)

def encrypt(plaintext: str, key: bytes) -> dict:
    """AES-256-GCM encrypt. Returns {nonce, ciphertext} as hex strings."""
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
    return {"nonce": nonce.hex(), "ciphertext": ciphertext.hex()}

def decrypt(encrypted: dict, key: bytes) -> str:
    """AES-256-GCM decrypt."""
    aesgcm = AESGCM(key)
    nonce = bytes.fromhex(encrypted["nonce"])
    ciphertext = bytes.fromhex(encrypted["ciphertext"])
    return aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')

def blind_index(text: str, key: bytes) -> str:
    """Create a searchable blind index without exposing plaintext."""
    return hashlib.blake2b(text.lower().encode('utf-8'), key=key[:32], digest_size=32).hexdigest()

import json

def encrypt_content(plaintext: str, key: bytes | None) -> str:
    if not key:
        return plaintext
    try:
        encrypted_dict = encrypt(plaintext, key)
        return json.dumps(encrypted_dict)
    except Exception:
        return plaintext

def decrypt_content(ciphertext: str, key: bytes | None) -> str:
    if not key:
        return ciphertext
    try:
        data = json.loads(ciphertext)
        if isinstance(data, dict) and "nonce" in data and "ciphertext" in data:
            return decrypt(data, key)
    except Exception:
        pass
    return ciphertext

