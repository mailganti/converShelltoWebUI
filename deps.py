from fastapi import Request, HTTPException
from controller.db.db import get_db
from controller.auth import normalize_identity
import logging

logger = logging.getLogger(__name__)


def _safe_username(value):
    if isinstance(value, str):
        v = value.strip()
        return v if v else None
    return None


def get_anonymous_user():
    return {
        "id": None,
        "username": "anonymous",
        "roles": []
    }


def get_runtime_user_from_request(request: Request):
    """
    Resolve runtime user from request headers.
    Hardened to avoid SQLite parameter binding errors.
    """

    hdr_user = (
        request.headers.get("X-Auth-User")
        or request.headers.get("X-Client-Cert-CN")
        or request.headers.get("X-Forwarded-User")
        or request.headers.get("X-Remote-User")
    )

    normalized = _safe_username(normalize_identity(hdr_user))
    raw_username = _safe_username(hdr_user)

    db = get_db()
    user = None

    if normalized:
        user = db.get_user_by_username(normalized)

    if not user and raw_username and raw_username != normalized:
        user = db.get_user_by_username(raw_username)

    if not user:
        logger.warning(
            "Unable to resolve user from request. hdr_user=%r type=%s",
            hdr_user, type(hdr_user).__name__
        )
        return get_anonymous_user()

    return user
