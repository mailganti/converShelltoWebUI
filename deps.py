"""
controller/deps.py

Authentication / Authorization dependencies for the Orchestration System.
Supports both Smart Card / Windows Auth (via proxy headers) and token-based auth.
"""

from __future__ import annotations

import os
import re
import logging
from datetime import datetime
from typing import Optional, Dict, Any

import jwt  # For exception types
from fastapi import Request, Header, Depends, HTTPException, status

from controller.db.db import get_db

logger = logging.getLogger(__name__)


# -------------------------------------------------------------
# Identity Normalization
# -------------------------------------------------------------
def normalize_identity(raw: str) -> str:
    """
    Convert arbitrary identity strings into a clean username.

    Examples:
      'U\\Rajesh Mudiganti (affiliate)' → 'Rajesh Mudiganti'
      'DOMAIN\\jsmith' → 'jsmith'
      'jsmith@acme.com' → 'jsmith'
    """
    if not raw:
        return ""

    s = raw.strip()

    # Remove quotes
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()

    # Remove any trailing parentheses text
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s).strip()

    # DOMAIN\username → username
    if "\\" in s:
        s = s.split("\\", 1)[1].strip()

    # user@domain.com → user
    if "@" in s:
        s = s.split("@", 1)[0]

    # Remove weird U\ prefix again if still present
    s = re.sub(r"^[A-Za-z]\\", "", s).strip()

    # Collapse double spaces
    s = re.sub(r"\s+", " ", s)

    return s


# -------------------------------------------------------------
# Build runtime user from proxy headers + DB role merge
# -------------------------------------------------------------
def get_runtime_user_from_request(request: Request) -> Optional[Dict[str, Any]]:
    """
    Build a unified user object from proxy headers.
    Returns None if no identity found.
    """
    hdr_user = (
        request.headers.get("X-Auth-User")
        or request.headers.get("X-Client-Cert-CN")
        or request.headers.get("X-Forwarded-User")
        or request.headers.get("X-Remote-User")
    )

    if not hdr_user:
        return None

    normalized = normalize_identity(hdr_user)
    raw_username = hdr_user.strip()
    
    # Remove quotes from raw if present
    if (raw_username.startswith('"') and raw_username.endswith('"')) or \
       (raw_username.startswith("'") and raw_username.endswith("'")):
        raw_username = raw_username[1:-1].strip()

    runtime_user = {
        "username": normalized,
        "display_name": normalized.replace(".", " ").replace("_", " ").title(),
        "role": None,
        "user_id": None,
        "auth_method": request.headers.get("X-Auth-Method") or "proxy",
        "token_name": normalized,
    }

    # Merge with DB user record - try normalized first, then raw
    try:
        db = get_db()
        user = db.get_user_by_username(normalized)
        
        # If normalized lookup fails, try raw username (e.g., "John Snow (affiliate)")
        if not user and raw_username != normalized:
            user = db.get_user_by_username(raw_username)
            if user:
                logger.debug(f"User found with raw username: {raw_username}")
        
        if user:
            runtime_user["role"] = user.get("role")
            runtime_user["user_id"] = user.get("user_id") or user.get("id")
            runtime_user["display_name"] = user.get("full_name") or runtime_user["display_name"]
    except Exception:
        logger.exception("Failed to merge user with DB")

    return runtime_user


# -------------------------------------------------------------
# Token-based Authentication
# -------------------------------------------------------------
def verify_token(request: Request) -> Dict[str, Any]:
    """
    Verify authentication - supports both header-based and token-based auth.
    
    Checks in order:
    1. Proxy headers (X-Auth-User, X-Client-Cert-CN, etc.)
    2. X-Admin-Token header
    3. X-Agent-Token header
    """
    # First try proxy headers (Smart Card / WNA)
    user = get_runtime_user_from_request(request)
    if user and user.get("username"):
        return user
    
    # Try X-Admin-Token
    admin_token = request.headers.get("X-Admin-Token")
    if admin_token:
        db = get_db()
        token_row = db.get_token_by_value(admin_token)
        if token_row and token_row.get("revoked") != 1:
            return {
                "username": token_row.get("token_name"),
                "token_name": token_row.get("token_name"),
                "role": token_row.get("role"),
                "auth_method": "token",
            }
        raise HTTPException(status_code=401, detail="Invalid or revoked admin token")
    
    # Try X-Agent-Token  
    agent_token = request.headers.get("X-Agent-Token")
    if agent_token:
        db = get_db()
        token_row = db.get_token_by_value(agent_token)
        if token_row and token_row.get("revoked") != 1:
            if token_row.get("role") != "agent":
                raise HTTPException(status_code=403, detail="Token is not an agent token")
            return {
                "username": token_row.get("token_name"),
                "token_name": token_row.get("token_name"),
                "role": "agent",
                "auth_method": "agent_token",
            }
        raise HTTPException(status_code=401, detail="Invalid or revoked agent token")
    
    raise HTTPException(status_code=401, detail="Authentication required")


# -------------------------------------------------------------
# Dependencies
# -------------------------------------------------------------
def require_authenticated_user(request: Request) -> Dict[str, Any]:
    """Require any form of authentication."""
    return verify_token(request)


def require_admin(request: Request) -> Dict[str, Any]:
    """
    Require admin role.
    Smart Card/WNA authenticated users are trusted as admins.
    """
    user = verify_token(request)
    role = user.get("role")
    
    # If role is admin, allow
    if role == "admin":
        return user
    
    # Smart Card / proxy authenticated users are trusted as admins
    # (they passed strong enterprise authentication)
    auth_method = user.get("auth_method", "")
    if auth_method in ("proxy", "smartcard", "wna"):
        logger.info(f"Admin access granted to {user.get('username')} via {auth_method}")
        user["role"] = "admin"
        return user
    
    raise HTTPException(status_code=403, detail="Admin access required")


def require_approver(request: Request) -> Dict[str, Any]:
    """
    Require approver or admin role.
    Smart Card/WNA authenticated users are trusted as approvers.
    """
    user = verify_token(request)
    role = user.get("role")
    
    # If role is approver or admin, allow
    if role in ("approver", "admin"):
        return user
    
    # Smart Card / proxy authenticated users are trusted as approvers
    # (they passed strong enterprise authentication)
    auth_method = user.get("auth_method", "")
    if auth_method in ("proxy", "smartcard", "wna"):
        logger.info(f"Approver access granted to {user.get('username')} via {auth_method}")
        user["role"] = "approver"
        return user
    
    raise HTTPException(status_code=403, detail="Approver access required")


def require_agent(request: Request) -> Dict[str, Any]:
    """Require agent token specifically (X-Agent-Token header)."""
    agent_token = request.headers.get("X-Agent-Token") or request.headers.get("X-Agent-Auth")
    if not agent_token:
        raise HTTPException(status_code=401, detail="Agent token required (X-Agent-Token header)")
    
    db = get_db()
    token_row = db.get_token_by_value(agent_token)
    
    if not token_row or token_row.get("revoked") == 1:
        raise HTTPException(status_code=401, detail="Invalid or revoked agent token")
    
    if token_row.get("role") != "agent":
        raise HTTPException(status_code=403, detail="Token is not an agent token")
    
    return {
        "username": token_row.get("token_name"),
        "token_name": token_row.get("token_name"),
        "role": "agent",
        "auth_method": "agent_token",
    }


# -------------------------------------------------------------
# Approver JWT for workflow approvals
# -------------------------------------------------------------
def verify_approver_jwt(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    FastAPI dependency to verify approver JWT from Authorization header.
    """
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Invalid Authorization header")

    token = authorization.split(" ", 1)[1].strip()

    try:
        # Import from auth module
        from controller.auth.approver_jwt import verify_approver_jwt as verify_jwt
        payload = verify_jwt(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Approver token expired")
    except Exception:
        raise HTTPException(401, "Invalid approver token")

    if payload.get("role") not in ("approver", "admin"):
        raise HTTPException(403, "Approver role required")

    return payload


# -------------------------------------------------------------
# Execution Token Dependency (One-Time Tokens)
# -------------------------------------------------------------
def require_execution_token(workflow_id: str):
    def _dep(
        request: Request,
        token: Optional[str] = Header(None, alias="X-Execution-Token"),
    ):
        user = verify_token(request)
        
        if not token:
            raise HTTPException(403, "Execution token required")

        db = get_db()
        token_row = db.get_execution_token_by_value(token)
        if not token_row:
            raise HTTPException(403, "Invalid execution token")

        if str(token_row.get("workflow_id")) != str(workflow_id):
            raise HTTPException(403, "Token not valid for this workflow")

        if token_row.get("used"):
            raise HTTPException(403, "Token already used")

        expires_at = token_row.get("expires_at")
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at)
                if exp < datetime.utcnow():
                    raise HTTPException(403, "Token expired")
            except Exception:
                logger.error("Invalid expires_at format: %s", expires_at)

        ok = db.mark_execution_token_used(token_row["id"], user["username"])
        if not ok:
            raise HTTPException(403, "Token could not be consumed")

        return token_row

    return _dep
