"""Optional OIDC / JWT verification.

Gates the API on a valid OIDC id_token (JWT) — verified in-process so it
composes with SSE response streaming (a gateway authorizer that buffers would
break the live feed).

Flow:
  1. Client sends `Authorization: Bearer <id_token>` (an OIDC id_token) — or,
     for the SSE GET where some clients can't set headers, `?access_token=`.
  2. We fetch the provider's public signing keys (JWKS), cached hourly.
  3. Verify the RS256 signature, issuer, and expiry (and audience if configured).
  4. On success, the caller's claims are returned; else 401.

Enable with REQUIRE_AUTH=true and set OIDC_ISSUER / OIDC_JWKS_URL. Off by default
so local/mock dev needs no auth. Works with any standard OIDC provider
(Cognito, Auth0, Okta, Google, Entra ID, etc.).
"""
from __future__ import annotations

import time

import jwt
from fastapi import Header, HTTPException, Request
from jwt import PyJWKClient

from .config import get_settings

# Module-level JWKS client cache (PyJWKClient caches keys internally too).
_jwk_client: PyJWKClient | None = None
_jwk_client_ts: float = 0.0
_JWK_TTL = 3600  # refresh the client hourly


def _jwks() -> PyJWKClient:
    global _jwk_client, _jwk_client_ts
    now = time.time()
    if _jwk_client is None or (now - _jwk_client_ts) > _JWK_TTL:
        _jwk_client = PyJWKClient(get_settings().oidc_jwks_url)
        _jwk_client_ts = now
    return _jwk_client


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def verify_token(token: str) -> dict:
    """Verify an OIDC id_token and return its claims. Raises on failure."""
    s = get_settings()
    signing_key = _jwks().get_signing_key_from_jwt(token).key
    options = {"verify_aud": bool(s.oidc_audience_list)}
    return jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        issuer=s.oidc_issuer or None,
        audience=s.oidc_audience_list or None,
        options=options,
    )


async def require_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    """FastAPI dependency. No-op when REQUIRE_AUTH is false.

    Accepts the token from the `Authorization: Bearer` header, or (for the SSE
    GET, where some clients can't set headers) a `?access_token=` query param.
    Returns the token claims; the user id is typically claims['sub'].
    """
    s = get_settings()
    if not s.require_auth:
        return {"sub": "local-dev", "anonymous": True}

    token = _extract_bearer(authorization) or request.query_params.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        claims = verify_token(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    return claims
