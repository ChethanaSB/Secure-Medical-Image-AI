"""
supabase_auth.py - Supabase-backed authentication service.

Uses the Supabase REST API (GoTrue) for:
  - User sign-up (email/password with profile metadata)
  - User sign-in (email/password)
  - Session validation via Supabase JWT

Also stores extended profile data (name, phone, role) in a
public 'profiles' table via the Supabase PostgREST API.

Required env vars:
  SUPABASE_URL  — e.g. https://abcxyz.supabase.co
  SUPABASE_KEY  — anon (public) API key
"""

import os
import logging
import requests

log = logging.getLogger(__name__)


def _get_config():
    """Lazy-load Supabase config from env (picks up .env changes on restart)."""
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_KEY", "")
    return url, key


def _get_headers():
    """Return base headers with current API key."""
    _, key = _get_config()
    return {
        "apikey": key,
        "Content-Type": "application/json",
    }


def _auth_headers(access_token: str | None = None) -> dict:
    """Return headers for Supabase requests."""
    _, key = _get_config()
    h = _get_headers()
    if access_token:
        h["Authorization"] = f"Bearer {access_token}"
    else:
        h["Authorization"] = f"Bearer {key}"
    return h


# ---------------------------------------------------------------------------
# Sign Up
# ---------------------------------------------------------------------------
def supabase_sign_up(email: str, password: str, name: str, phone: str, role: str = "doctor") -> dict:
    """
    Register a new user with Supabase Auth and create a profile row.

    Returns:
        {"success": True, "user": {...}, "session": {...}} on success
        {"success": False, "error": "..."} on failure
    """
    url, key = _get_config()
    if not url or not key:
        return {"success": False, "error": "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY in .env"}

    auth_url = f"{url}/auth/v1"
    rest_url = f"{url}/rest/v1"

    # 1. Create auth user via GoTrue
    payload = {
        "email": email,
        "password": password,
        "data": {
            "name": name,
            "phone": phone,
            "role": role,
        },
    }

    try:
        resp = requests.post(
            f"{auth_url}/signup",
            json=payload,
            headers=_get_headers(),
            timeout=15,
        )
        data = resp.json()

        if resp.status_code not in (200, 201):
            error_msg = data.get("error_description") or data.get("msg") or data.get("message") or str(data)
            return {"success": False, "error": error_msg}

        user_data = data.get("user", data)
        user_id = user_data.get("id", "")
        access_token = data.get("access_token", "")

        # 2. Upsert profile in 'profiles' table
        profile_payload = {
            "id": user_id,
            "name": name,
            "email": email,
            "phone": phone,
            "role": role,
        }

        profile_headers = _auth_headers(access_token if access_token else None)
        profile_headers["Prefer"] = "resolution=merge-duplicates"

        requests.post(
            f"{rest_url}/profiles",
            json=profile_payload,
            headers=profile_headers,
            timeout=10,
        )

        return {
            "success": True,
            "user": {
                "id": user_id,
                "email": email,
                "name": name,
                "phone": phone,
                "role": role,
            },
            "session": {
                "access_token": data.get("access_token", ""),
                "refresh_token": data.get("refresh_token", ""),
                "expires_in": data.get("expires_in", 3600),
            },
        }

    except requests.RequestException as exc:
        log.error("Supabase sign-up request failed: %s", exc)
        return {"success": False, "error": f"Network error: {exc}"}


# ---------------------------------------------------------------------------
# Sign In
# ---------------------------------------------------------------------------
def supabase_sign_in(email: str, password: str) -> dict:
    """
    Authenticate a user via Supabase GoTrue (email+password).

    Returns:
        {"success": True, "user": {...}, "session": {...}} on success
        {"success": False, "error": "..."} on failure
    """
    url, key = _get_config()
    if not url or not key:
        return {"success": False, "error": "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY in .env"}

    auth_url = f"{url}/auth/v1"

    payload = {
        "email": email,
        "password": password,
    }

    try:
        resp = requests.post(
            f"{auth_url}/token?grant_type=password",
            json=payload,
            headers=_get_headers(),
            timeout=15,
        )
        data = resp.json()

        if resp.status_code != 200:
            error_msg = data.get("error_description") or data.get("msg") or data.get("message") or str(data)
            return {"success": False, "error": error_msg}

        user_data = data.get("user", {})
        user_id = user_data.get("id", "")
        meta = user_data.get("user_metadata", {})
        access_token = data.get("access_token", "")

        # Fetch profile from profiles table for latest role/phone
        profile = _fetch_profile(user_id, access_token)

        return {
            "success": True,
            "user": {
                "id": user_id,
                "email": user_data.get("email", ""),
                "name": profile.get("name", meta.get("name", "")),
                "phone": profile.get("phone", meta.get("phone", "")),
                "role": profile.get("role", meta.get("role", "doctor")),
            },
            "session": {
                "access_token": access_token,
                "refresh_token": data.get("refresh_token", ""),
                "expires_in": data.get("expires_in", 3600),
            },
        }

    except requests.RequestException as exc:
        log.error("Supabase sign-in request failed: %s", exc)
        return {"success": False, "error": f"Network error: {exc}"}


# ---------------------------------------------------------------------------
# Validate Token (used by jwt_required decorator)
# ---------------------------------------------------------------------------
def supabase_get_user(access_token: str) -> dict | None:
    """
    Validate a Supabase access token and return user info.
    Returns None if the token is invalid/expired.
    """
    url, key = _get_config()
    if not url or not key:
        return None

    auth_url = f"{url}/auth/v1"

    try:
        resp = requests.get(
            f"{auth_url}/user",
            headers=_auth_headers(access_token),
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        user_data = resp.json()
        user_id = user_data.get("id", "")
        meta = user_data.get("user_metadata", {})

        # Fetch profile
        profile = _fetch_profile(user_id, access_token)

        return {
            "id": user_id,
            "email": user_data.get("email", ""),
            "name": profile.get("name", meta.get("name", "")),
            "phone": profile.get("phone", meta.get("phone", "")),
            "role": profile.get("role", meta.get("role", "doctor")),
        }

    except requests.RequestException:
        return None


# ---------------------------------------------------------------------------
# Fetch profile from 'profiles' table
# ---------------------------------------------------------------------------
def _fetch_profile(user_id: str, access_token: str) -> dict:
    """Fetch a user's profile row from the 'profiles' table."""
    url, _ = _get_config()
    rest_url = f"{url}/rest/v1"

    try:
        resp = requests.get(
            f"{rest_url}/profiles?id=eq.{user_id}&select=*",
            headers=_auth_headers(access_token),
            timeout=10,
        )
        if resp.status_code == 200:
            rows = resp.json()
            if rows and len(rows) > 0:
                return rows[0]
    except requests.RequestException:
        pass
    return {}


# ---------------------------------------------------------------------------
# List all users (admin)
# ---------------------------------------------------------------------------
def supabase_list_users(access_token: str) -> list:
    """Fetch all profiles (for admin dashboard)."""
    url, _ = _get_config()
    rest_url = f"{url}/rest/v1"

    try:
        headers = _auth_headers(access_token)
        resp = requests.get(
            f"{rest_url}/profiles?select=*&order=created_at.desc",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except requests.RequestException:
        pass
    return []
