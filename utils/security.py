"""
security.py - Security utilities:
  - Password hashing / verification via bcrypt
  - JWT creation and decoding
  - Login attempt rate-limiting (in-memory, per-IP)
  - Role-based access middleware decorator
"""

import os
import jwt
import datetime
from functools import wraps
from collections import defaultdict

import bcrypt
from flask import request, jsonify, current_app, g

# ---------------------------------------------------------------------------
# Password helpers
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
# JWT helpers
# ---------------------------------------------------------------------------

def generate_token(user_id: int, role: str) -> str:
    """
    Create a signed JWT containing user_id and role.
    Expiry: JWT_EXPIRY_HOURS (env) or 24 h default.
    """
    secret = current_app.config["JWT_SECRET_KEY"]
    expiry_hours = int(os.getenv("JWT_EXPIRY_HOURS", 24))

    payload = {
        "sub": user_id,
        "role": role,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=expiry_hours),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT.
    Returns the payload dict, or raises jwt.ExpiredSignatureError / jwt.InvalidTokenError.
    """
    secret = current_app.config["JWT_SECRET_KEY"]
    return jwt.decode(token, secret, algorithms=["HS256"])


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
# JWT Authentication decorator
# ---------------------------------------------------------------------------

def jwt_required(f):
    """
    Decorator that validates the Bearer JWT in the Authorization header.
    On success, sets g.current_user = {"id": ..., "role": ...}.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header."}), 401

        token = auth_header.split(" ", 1)[1]
        try:
            payload = decode_token(token)
            g.current_user = {"id": payload["sub"], "role": payload["role"]}
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token."}), 401

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
