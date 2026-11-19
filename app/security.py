"""Criptografia de segredos persistidos."""
import os
from cryptography.fernet import Fernet


def cipher():
    key = os.environ.get("FERNET_KEY")
    if not key:
        raise RuntimeError("Configure FERNET_KEY no .env antes de salvar credenciais")
    return Fernet(key.encode())


def encrypt(value):
    return cipher().encrypt(value.encode()).decode()


def decrypt(value):
    return cipher().decrypt(value.encode()).decode()
