"""Encrypt the trusted model for storage without publishing the plaintext pickle."""

from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b"kkpsf-extra-trees-v1"


def _key() -> bytes:
    encoded = os.getenv("MODEL_DECRYPT_KEY_B64", "")
    if not encoded:
        raise ValueError("MODEL_DECRYPT_KEY_B64 is required")
    key = base64.b64decode(encoded, validate=True)
    if len(key) != 32:
        raise ValueError("Model key must be 32 bytes")
    return key


def encrypt(source: Path, target: Path) -> None:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, source.read_bytes(), AAD)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(nonce + ciphertext)


def decrypt(source: Path, target: Path) -> None:
    data = source.read_bytes()
    if len(data) < 29:
        raise ValueError("Encrypted model is too short")
    plaintext = AESGCM(_key()).decrypt(data[:12], data[12:], AAD)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(plaintext)


def main() -> None:
    parser = argparse.ArgumentParser(description="Encrypt or decrypt the trusted Extra Trees model")
    parser.add_argument("action", choices=("encrypt", "decrypt"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    (encrypt if args.action == "encrypt" else decrypt)(args.input, args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
