from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from app.config import Settings


@dataclass(slots=True)
class AdminToken:
    token: str
    expires_at: float


class AdminSecurity:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._tokens: dict[str, float] = {}
        self._failures: dict[str, tuple[int, float]] = {}

    def verify_password(self, password: str) -> bool:
        if not self.settings.has_admin_credentials:
            return False
        candidate = hashlib.sha256(password.encode("utf-8")).hexdigest()
        if self.settings.admin_password_sha256:
            return hmac.compare_digest(candidate, self.settings.admin_password_sha256.strip().lower())
        return hmac.compare_digest(password, self.settings.admin_password)

    def login(self, password: str, client_id: str) -> AdminToken | None:
        now = time.time()
        failures, blocked_until = self._failures.get(client_id, (0, 0.0))
        if blocked_until > now:
            return None
        if not self.verify_password(password):
            failures += 1
            blocked_until = now + 900 if failures >= 5 else 0.0
            self._failures[client_id] = (failures, blocked_until)
            return None
        self._failures.pop(client_id, None)
        token = secrets.token_urlsafe(32)
        expires = now + self.settings.admin_token_ttl_seconds
        self._tokens[token] = expires
        return AdminToken(token, expires)

    def verify_token(self, token: str | None) -> bool:
        if not token:
            return False
        expires = self._tokens.get(token)
        if expires is None:
            return False
        if expires < time.time():
            self._tokens.pop(token, None)
            return False
        return True

    def revoke(self, token: str) -> None:
        self._tokens.pop(token, None)
