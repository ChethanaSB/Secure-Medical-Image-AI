"""
security.py - Security utilities (Supabase + local DB hybrid):
  - Supabase JWT validation via /auth/v1/user
  - Auto-sync Supabase user → local SQLite User record (FK compat)
  - Password hashing / verification via bcrypt (kept for legacy seed)
  - Role-based access middleware decorator
  - Login attempt rate-limiting (in-memory, per-IP)
"""

import os
import datetime
from functools import wraps
from collections import defaultdict

import bcrypt
from flask import request, jsonify, current_app, g

from utils.supabase_auth import supabase_get_user

# ---------------------------------------------------------------------------
# Password helpers (kept for seed_admin and legacy compatibility)
# ---------------------------------------------------------------------------

def hash_password(plain_text: str) -> str:
    """Return a bcrypt-hashed version of plain_text (stored as str)."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain_text.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_text: str, password_hash: str) -> bool:
    """Return True if plain_text matches the stored bcrypt hash."""
    return bcrypt.checkpw(
        plain_text.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


# ---------------------------------------------------------------------------
# Login attempt limiter (in-memory, keyed by IP address)
# ---------------------------------------------------------------------------

_login_attempts: dict = defaultdict(lambda: {"count": 0, "lockout_until": None})

MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", 5))
LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", 15))


def get_client_ip() -> str:
    """Return the best-guess client IP (respects X-Forwarded-For)."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


def is_ip_locked(ip: str) -> tuple[bool, str]:
    """
    Check whether an IP is currently locked out.
    Returns (locked: bool, reason: str).
    """
    record = _login_attempts[ip]
    if record["lockout_until"] is not None:
        if datetime.datetime.utcnow() < record["lockout_until"]:
            remaining = (record["lockout_until"] - datetime.datetime.utcnow()).seconds // 60 + 1
            return True, f"Too many failed login attempts. Try again in {remaining} minute(s)."
        else:
            # Lockout expired – reset
            record["count"] = 0
            record["lockout_until"] = None
    return False, ""


def record_failed_attempt(ip: str):
    """Increment failed attempt counter; enforce lockout when limit is reached."""
    record = _login_attempts[ip]
    record["count"] += 1
    if record["count"] >= MAX_LOGIN_ATTEMPTS:
        record["lockout_until"] = datetime.datetime.utcnow() + datetime.timedelta(minutes=LOCKOUT_MINUTES)


def reset_attempts(ip: str):
    """Clear failed attempts after a successful login."""
    _login_attempts[ip] = {"count": 0, "lockout_until": None}


# ---------------------------------------------------------------------------
# Supabase user → local User sync
# ---------------------------------------------------------------------------

def _sync_local_user(supabase_user: dict) -> int:
    """
    Ensure a local SQLite User record exists for this Supabase user.
    Returns the local integer user_id for FK compatibility.
    """
    from models.user_model import User
    from utils.db import db

    supabase_id = supabase_user.get("id", "")
    email = supabase_user.get("email", "")
    name = supabase_user.get("name", email)
    role = supabase_user.get("role", "doctor")

    # Look up by supabase_id first
    local_user = User.query.filter_by(supabase_id=supabase_id).first()
    if local_user:
        # Update role if changed
        if local_user.role != role:
            local_user.role = role
            db.session.commit()
        return local_user.user_id

    # Look up by username (email) as fallback
    local_user = User.query.filter_by(username=email).first()
    if local_user:
        local_user.supabase_id = supabase_id
        if local_user.role != role:
            local_user.role = role
        db.session.commit()
        return local_user.user_id

    # Create new local user
    new_user = User(
        username=name if name else email,
        password_hash="supabase-managed",
        role=role,
        supabase_id=supabase_id,
    )
    db.session.add(new_user)
    db.session.commit()
    return new_user.user_id


# ---------------------------------------------------------------------------
# JWT Authentication decorator (Supabase-backed)
# ---------------------------------------------------------------------------

def jwt_required(f):
    """
    Decorator that validates the Bearer JWT via Supabase's /auth/v1/user
    endpoint.  On success, sets g.current_user = {"id": <local_int>, "role": ...}.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header."}), 401

        token = auth_header.split(" ", 1)[1]

        # Validate with Supabase
        supabase_user = supabase_get_user(token)
        if not supabase_user:
            return jsonify({"error": "Invalid or expired token."}), 401

        # Sync to local DB and get integer user_id
        local_user_id = _sync_local_user(supabase_user)

        g.current_user = {
            "id": local_user_id,
            "role": supabase_user.get("role", "doctor"),
            "email": supabase_user.get("email", ""),
            "name": supabase_user.get("name", ""),
        }
        g.access_token = token

        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Role-based access decorator
# ---------------------------------------------------------------------------

def roles_required(*allowed_roles):
    """
    Decorator (must be placed AFTER @jwt_required) that restricts endpoint
    access to users whose role is in allowed_roles.

    Usage:
        @jwt_required
        @roles_required("admin", "doctor")
        def my_view():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_role = getattr(g, "current_user", {}).get("role")
            if user_role not in allowed_roles:
                return jsonify({
                    "error": f"Access denied. Requires one of: {', '.join(allowed_roles)}."
                }), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ---------------------------------------------------------------------------
# Legacy JWT helpers (kept for backward compatibility but no longer primary)
# ---------------------------------------------------------------------------

def generate_token(user_id: int, role: str) -> str:
    """Create a signed JWT (legacy — Supabase tokens are now primary)."""
    import jwt as pyjwt
    secret = current_app.config["JWT_SECRET_KEY"]
    expiry_hours = int(os.getenv("JWT_EXPIRY_HOURS", 24))
    payload = {
        "sub": user_id,
        "role": role,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=expiry_hours),
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Decode a legacy JWT (fallback)."""
    import jwt as pyjwt
    secret = current_app.config["JWT_SECRET_KEY"]
    return pyjwt.decode(token, secret, algorithms=["HS256"])
