"""
auth_routes.py - Authentication Blueprint.

Endpoints:
  POST /auth/register  — Admin-only: create a new user account
  POST /auth/login     — Public: authenticate and receive a JWT
  GET  /auth/me        — Protected: return current user info
  GET  /auth/users     — Admin-only: list all users
"""

from flask import Blueprint, request, jsonify, g

from models.user_model import User
from utils.db import db
from utils.security import (
    hash_password,
    verify_password,
    generate_token,
    jwt_required,
    roles_required,
    get_client_ip,
    is_ip_locked,
    record_failed_attempt,
    reset_attempts,
)
from utils.audit import (
    write_audit,
    LOGIN_SUCCESS, LOGIN_FAILED, LOGIN_LOCKED,
    USER_REGISTERED, USER_DELETED,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ---------------------------------------------------------------------------
# Allowed roles constant
# ---------------------------------------------------------------------------
VALID_ROLES = {"admin", "doctor", "radiologist"}


# ---------------------------------------------------------------------------
# POST /auth/register  (Admin only)
# ---------------------------------------------------------------------------
@auth_bp.route("/register", methods=["POST"])
@jwt_required
@roles_required("admin")
def register():
    """
    Register a new user.
    Requires: Bearer JWT with role=admin.
    Body (JSON): { "username": str, "password": str, "role": str }
    """
    data = request.get_json(silent=True) or {}

    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "").strip().lower()

    # --- Validation ---
    if not username or not password or not role:
        return jsonify({"error": "username, password, and role are required."}), 400

    if len(username) < 3 or len(username) > 80:
        return jsonify({"error": "username must be 3–80 characters."}), 400

    if len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters."}), 400

    if role not in VALID_ROLES:
        return jsonify({"error": f"role must be one of: {', '.join(VALID_ROLES)}."}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists."}), 409

    # --- Create user ---
    new_user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
    )
    db.session.add(new_user)
    db.session.flush()   # get new_user.user_id before commit

    write_audit(
        USER_REGISTERED,
        user_id=g.current_user["id"],
        target_type="user",
        target_id=new_user.user_id,
        details={"new_username": username, "role": role},
        ip=get_client_ip(),
    )
    db.session.commit()

    return jsonify({
        "message": "User registered successfully.",
        "user": new_user.to_dict(),
    }), 201


# ---------------------------------------------------------------------------
# POST /auth/login  (Public)
# ---------------------------------------------------------------------------
@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticate a user and return a signed JWT.
    Applies IP-based brute-force protection.
    Body (JSON): { "username": str, "password": str }
    """
    ip = get_client_ip()

    # --- Rate-limit check ---
    locked, lock_msg = is_ip_locked(ip)
    if locked:
        write_audit(LOGIN_LOCKED, ip=ip,
                    details={"attempted_username": (data := request.get_json(silent=True) or {}).get("username", "")})
        db.session.commit()
        return jsonify({"error": lock_msg}), 429

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "username and password are required."}), 400

    user = User.query.filter_by(username=username).first()

    # Use a constant-time check to prevent timing attacks
    if not user or not verify_password(password, user.password_hash):
        record_failed_attempt(ip)
        write_audit(LOGIN_FAILED, ip=ip,
                    details={"attempted_username": username,
                             "reason": "invalid_credentials"})
        db.session.commit()
        # Re-check to inform user if they just got locked
        locked, lock_msg = is_ip_locked(ip)
        if locked:
            return jsonify({"error": lock_msg}), 429
        return jsonify({"error": "Invalid username or password."}), 401

    # --- Successful login ---
    reset_attempts(ip)
    token = generate_token(user.user_id, user.role)

    write_audit(
        LOGIN_SUCCESS,
        user_id=user.user_id,
        target_type="user",
        target_id=user.user_id,
        details={"username": user.username, "role": user.role},
        ip=ip,
    )
    db.session.commit()

    return jsonify({
        "message": "Login successful.",
        "token": token,
        "user": user.to_dict(),
    }), 200


# ---------------------------------------------------------------------------
# GET /auth/me  (Protected — any authenticated user)
# ---------------------------------------------------------------------------
@auth_bp.route("/me", methods=["GET"])
@jwt_required
def me():
    """Return the currently authenticated user's profile."""
    user = db.session.get(User, g.current_user["id"])
    if not user:
        return jsonify({"error": "User not found."}), 404
    return jsonify({"user": user.to_dict()}), 200


# ---------------------------------------------------------------------------
# GET /auth/users  (Admin only)
# ---------------------------------------------------------------------------
@auth_bp.route("/users", methods=["GET"])
@jwt_required
@roles_required("admin")
def list_users():
    """Return a paginated list of all registered users."""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    pagination = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
        "users": [u.to_dict() for u in pagination.items],
    }), 200


# ---------------------------------------------------------------------------
# DELETE /auth/users/<user_id>  (Admin only)
# ---------------------------------------------------------------------------
@auth_bp.route("/users/<int:user_id>", methods=["DELETE"])
@jwt_required
@roles_required("admin")
def delete_user(user_id: int):
    """Delete a user by ID. Admins cannot delete themselves."""
    if g.current_user["id"] == user_id:
        return jsonify({"error": "You cannot delete your own account."}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    username = user.username
    db.session.delete(user)

    write_audit(
        USER_DELETED,
        user_id=g.current_user["id"],
        target_type="user",
        target_id=user_id,
        details={"deleted_username": username},
        ip=get_client_ip(),
    )
    db.session.commit()
    return jsonify({"message": f"User '{username}' deleted successfully."}), 200
