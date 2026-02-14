# keycloak_auth.py
"""
Keycloak JWT token validation for FastAPI.
Validates access tokens issued by the corporate Keycloak server.
"""

import os
import time
import logging
from typing import Optional

import httpx
from jose import jwt, JWTError, jwk
from jose.utils import base64url_decode
from fastapi import Request, HTTPException

logger = logging.getLogger("kp-api")

# --- Configuration ---
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://auth.nir.center")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "platform")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "agent-kp")

OIDC_BASE = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
JWKS_URL = f"{OIDC_BASE}/protocol/openid-connect/certs"
ISSUER = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"

# --- JWKS Key Cache ---
_jwks_cache: Optional[dict] = None
_jwks_cache_time: float = 0
JWKS_CACHE_TTL = 3600  # Refresh keys every 60 minutes


def _fetch_jwks() -> dict:
    """Fetch JSON Web Key Set from Keycloak."""
    global _jwks_cache, _jwks_cache_time

    now = time.time()
    if _jwks_cache and (now - _jwks_cache_time) < JWKS_CACHE_TTL:
        return _jwks_cache

    for attempt in range(3):
        try:
            response = httpx.get(JWKS_URL, timeout=10)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_cache_time = now
            logger.info(f"Fetched JWKS keys from Keycloak ({len(_jwks_cache.get('keys', []))} keys)")
            return _jwks_cache
        except Exception as e:
            logger.warning(f"Attempt {attempt+1}/3 failed to fetch JWKS from {JWKS_URL}: {e}")
            if attempt < 2:
                time.sleep(2)
            else:
                logger.error(f"Final failure fetching JWKS: {e}")
    
    # If we have cached keys, use them even if expired
    if _jwks_cache:
        logger.warning("Using expired JWKS cache as fallback")
        return _jwks_cache
        
    raise HTTPException(
        status_code=503,
        detail="Authentication service unavailable (failed to fetch JWKS)"
    )


def _get_signing_key(token: str) -> dict:
    """Extract the correct signing key for the given token from JWKS."""
    jwks = _fetch_jwks()
    
    # Decode token header to get key ID (kid)
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token header: {e}")

    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Token missing key ID (kid)")

    # Find matching key
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key

    # Key not found — maybe keys rotated, force refresh
    global _jwks_cache_time
    _jwks_cache_time = 0
    jwks = _fetch_jwks()

    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key

    raise HTTPException(status_code=401, detail="Token signing key not found in JWKS")


def decode_token(token: str) -> dict:
    """Decode and validate a Keycloak JWT access token."""
    signing_key = _get_signing_key(token)

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience="account",  # Keycloak default audience
            issuer=ISSUER,
            options={
                "verify_aud": False,  # Keycloak SPA clients often don't have strict audience
                "verify_iss": False,
                "verify_exp": True,
            }
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning(f"Token expired: {token[:10]}...")
        raise HTTPException(status_code=401, detail="Token expired")
    except JWTError as e:
        logger.warning(f"Token validation failed: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def verify_keycloak_token(request: Request) -> str:
    """
    FastAPI dependency: validates Keycloak JWT from Authorization header.
    Returns the username (preferred_username from token).
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Expected: Bearer <token>"
        )

    token = auth_header.split(" ", 1)[1]
    payload = decode_token(token)

    # Extract username from token claims
    username = payload.get("preferred_username")
    if not username:
        # Fallback to other claims
        username = payload.get("sub")  # subject (UUID) as last resort

    if not username:
        raise HTTPException(status_code=401, detail="Token does not contain user identity")

    return username
