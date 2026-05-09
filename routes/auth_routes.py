"""
auth_routes.py - Authentication Blueprint (Supabase-backed).

Endpoints:
  POST /auth/register  — Public: create a new user account (name, email, password, phone)
  POST /auth/login     — Public: authenticate and receive a Supabase JWT
  GET  /auth/me        — Protected: return current user info
  GET  /auth/users     — Admin-only: list all users
"""

from flask import Blueprint, request, jsonify, g

from utils.supabase_auth import (
    supabase_sign_up,
    supabase_sign_in,
    supabase_list_users,
)
from utils.security import jwt_required, roles_required

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ---------------------------------------------------------------------------
# Allowed roles constant
# ---------------------------------------------------------------------------
VALID_ROLES = {"admin", "doctor", "radiologist"}


# ---------------------------------------------------------------------------
# POST /auth/register  (Public — self-registration)
# ---------------------------------------------------------------------------
@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Register a new user.
    Body (JSON): { "name": str, "email": str, "password": str, "phone": str, "role": str }
    """
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    phone = (data.get("phone") or "").strip()
    role = (data.get("role") or "doctor").strip().lower()

    # --- Validation ---
    if not name:
        return jsonify({"error": "Name is required."}), 400

    if not email:
        return jsonify({"error": "Email is required."}), 400

    if not password:
        return jsonify({"error": "Password is required."}), 400

    if len(name) < 2 or len(name) > 80:
        return jsonify({"error": "Name must be 2–80 characters."}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400

    if phone and (len(phone) < 10 or len(phone) > 15):
        return jsonify({"error": "Phone number must be 10–15 digits."}), 400

    if role not in VALID_ROLES:
        return jsonify({"error": f"Role must be one of: {', '.join(VALID_ROLES)}."}), 400

    # --- Create user via Supabase ---
    result = supabase_sign_up(email, password, name, phone, role)

    if not result["success"]:
        return jsonify({"error": result["error"]}), 400

    return jsonify({
        "message": "Registration successful! You can now sign in.",
        "user": result["user"],
        "session": result.get("session", {}),
    }), 201


# ---------------------------------------------------------------------------
# POST /auth/login  (Public)
# ---------------------------------------------------------------------------
@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticate a user and return a Supabase JWT.
    Body (JSON): { "email": str, "password": str }
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    result = supabase_sign_in(email, password)

    if not result["success"]:
        return jsonify({"error": result["error"]}), 401

    return jsonify({
        "message": "Login successful.",
        "token": result["session"]["access_token"],
        "user": result["user"],
        "session": result["session"],
    }), 200


# ---------------------------------------------------------------------------
# GET /auth/me  (Protected — any authenticated user)
# ---------------------------------------------------------------------------
@auth_bp.route("/me", methods=["GET"])
@jwt_required
def me():
    """Return the currently authenticated user's profile."""
    return jsonify({"user": g.current_user}), 200


# ---------------------------------------------------------------------------
# GET /auth/users  (Admin only)
# ---------------------------------------------------------------------------
@auth_bp.route("/users", methods=["GET"])
@jwt_required
@roles_required("admin")
def list_users():
    """Return a list of all registered users."""
    token = getattr(g, "access_token", "")
    users = supabase_list_users(token)
    return jsonify({
        "total": len(users),
        "users": users,
    }), 200
