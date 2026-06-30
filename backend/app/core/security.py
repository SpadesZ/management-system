# File Path: backend/app/core/security.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

import base64
import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass
class EncryptedSecretBundle:
    encrypted_secret: str
    encrypted_dek: str


class SecurityManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.master_cipher = self._build_master_cipher(self.settings.master_encryption_key)

    @staticmethod
    def _build_master_cipher(raw_key: str) -> Fernet:
        try:
            return Fernet(raw_key.encode("utf-8"))
        except ValueError:
            derived_key = base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode("utf-8")).digest())
            return Fernet(derived_key)

    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, subject: str, additional_claims: dict[str, Any] | None = None) -> str:
        expires_delta = timedelta(minutes=self.settings.jwt_expire_minutes)
        expire = datetime.now(UTC) + expires_delta
        payload: dict[str, Any] = {"sub": subject, "exp": expire}
        if additional_claims:
            payload.update(additional_claims)
        return jwt.encode(payload, self.settings.jwt_secret_key, algorithm=self.settings.jwt_algorithm)

    def decode_access_token(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(token, self.settings.jwt_secret_key, algorithms=[self.settings.jwt_algorithm])
        except JWTError as exc:
            raise ValueError("invalid token") from exc

    def envelope_encrypt_api_key(self, plain_secret: str) -> EncryptedSecretBundle:
        dek = Fernet.generate_key()
        dek_cipher = Fernet(dek)
        encrypted_secret = dek_cipher.encrypt(plain_secret.encode("utf-8")).decode("utf-8")
        encrypted_dek = self.master_cipher.encrypt(dek).decode("utf-8")
        return EncryptedSecretBundle(encrypted_secret=encrypted_secret, encrypted_dek=encrypted_dek)

    def envelope_decrypt_api_key(self, encrypted_secret: str, encrypted_dek: str) -> str:
        try:
            dek = self.master_cipher.decrypt(encrypted_dek.encode("utf-8"))
            dek_cipher = Fernet(dek)
            plain_secret = dek_cipher.decrypt(encrypted_secret.encode("utf-8"))
            return plain_secret.decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("decrypt failed") from exc

    @staticmethod
    def generate_trace_id() -> str:
        return base64.urlsafe_b64encode(os.urandom(18)).decode("utf-8").rstrip("=")


security_manager = SecurityManager()
