import hashlib
import secrets
from dataclasses import dataclass
from typing import Dict, Optional
from fastapi import Header, HTTPException, status
from app.config import settings


@dataclass(frozen=True)
class Principal:
    """Represents an authenticated caller/tenant."""
    principal_id: str
    org_id: str


def _hash_key(raw_key: str) -> str:
    """Securely hash an API key with SHA-256."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


class APIKeyRegistry:
    """
    Stores and validates API keys using secure cryptographic hashes.
    
    API keys are hashed and never stored or evaluated in plaintext.
    Keys are compared using constant-time comparison (secrets.compare_digest)
    to mitigate timing side-channel attacks.
    """
    def __init__(self):
        self._hashed_keys: Dict[str, Principal] = {}
        self._initialize_keys()

    def _initialize_keys(self) -> None:
        """Register development and configured API keys."""
        # 1. Registered dev/test keys
        default_keys = [
            ("test-api-key-org-a", "org_a"),
            ("API_KEY_A", "org_a"),
            ("test-api-key-org-b", "org_b"),
            ("API_KEY_B", "org_b"),
        ]
        for key_str, org in default_keys:
            self._hashed_keys[_hash_key(key_str)] = Principal(principal_id=org, org_id=org)

        # 2. Configured keys from environment (.env)
        if settings.api_key_a and settings.api_key_a != "replace-me-locally":
            self._hashed_keys[_hash_key(settings.api_key_a)] = Principal(
                principal_id="org_a", org_id="org_a"
            )
        if settings.api_key_b and settings.api_key_b != "replace-me-locally":
            self._hashed_keys[_hash_key(settings.api_key_b)] = Principal(
                principal_id="org_b", org_id="org_b"
            )

    def register_key(self, raw_key: str, org_id: str) -> None:
        """Register a new key mapping dynamically (for testing)."""
        self._hashed_keys[_hash_key(raw_key)] = Principal(principal_id=org_id, org_id=org_id)

    def authenticate(self, raw_key: Optional[str]) -> Optional[Principal]:
        """Validate raw key against stored hashes using constant-time comparison."""
        if not raw_key or not raw_key.strip():
            return None

        incoming_hash = _hash_key(raw_key)
        for stored_hash, principal in self._hashed_keys.items():
            if secrets.compare_digest(incoming_hash, stored_hash):
                return principal

        return None


api_key_registry = APIKeyRegistry()


def require_api_key(
    x_api_key: Optional[str] = Header(
        default=None,
        alias="X-API-Key",
        description="Tenant API key required for administrative link operations"
    )
) -> Principal:
    """
    FastAPI dependency: Enforces API Key authentication.
    Returns the authenticated Principal on success, raises 401 on missing or invalid key.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide the X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    principal = api_key_registry.authenticate(x_api_key)
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    return principal
