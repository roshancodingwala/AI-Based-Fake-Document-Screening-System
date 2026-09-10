"""
Authentication for the prototype.

Every route in this service is protected by a static API key passed in the
`X-API-Key` header. This is intentionally minimal — before production use,
replace with per-officer OAuth2/OIDC tokens, short-lived sessions, and
role-based access control (e.g. only supervisors can hit /fraud/confirmed).
"""
import logging

from fastapi import Header, HTTPException, status

from app.core.config import get_settings

logger = logging.getLogger("sentry_id.security")


async def require_api_key(x_api_key: str = Header(default=None, alias="X-API-Key")) -> str:
    settings = get_settings()

    if not x_api_key:
        logger.warning("security_event=missing_api_key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide it in the X-API-Key header.",
        )

    if x_api_key != settings.api_key:
        logger.warning("security_event=invalid_api_key")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )

    return x_api_key
