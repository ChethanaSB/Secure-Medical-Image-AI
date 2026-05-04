"""
validators.py - Server-side input validation helpers.

All validators return (valid: bool, value, error_message: str).
On success error_message is ""; on failure value is None.
"""

import re
import datetime


# ── String sanitisation ────────────────────────────────────────────────────

def sanitize(s: str | None, max_len: int = 200) -> str:
    """Strip whitespace and truncate to max_len.  Always returns a str."""
    if not isinstance(s, str):
        return ""
    return s.strip()[:max_len]


# ── User fields ────────────────────────────────────────────────────────────

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]{3,80}$")

def validate_username(raw: str | None) -> tuple[bool, str, str]:
    val = sanitize(raw)
    if not val:
        return False, "", "username is required."
    if len(val) < 3:
        return False, "", "username must be at least 3 characters."
    if len(val) > 80:
        return False, "", "username must be 80 characters or fewer."
    if not _USERNAME_RE.match(val):
        return False, "", "username may only contain letters, digits, ., _, -"
    return True, val, ""


def validate_password(raw: str | None) -> tuple[bool, str, str]:
    if not raw or len(raw) < 8:
        return False, "", "password must be at least 8 characters."
    if len(raw) > 128:
        return False, "", "password must be 128 characters or fewer."
    return True, raw, ""


def validate_role(raw: str | None, allowed: set[str]) -> tuple[bool, str, str]:
    val = sanitize(raw).lower()
    if val not in allowed:
        return False, "", f"role must be one of: {', '.join(sorted(allowed))}."
    return True, val, ""


# ── Patient fields ─────────────────────────────────────────────────────────

def validate_patient_id(raw) -> tuple[bool, int, str]:
    try:
        pid = int(raw)
        if pid < 1:
            return False, 0, "patient_id must be a positive integer."
        return True, pid, ""
    except (TypeError, ValueError):
        return False, 0, "patient_id must be an integer."


def validate_name(raw: str | None, field: str = "name") -> tuple[bool, str, str]:
    val = sanitize(raw, 120)
    if not val:
        return False, "", f"{field} is required."
    return True, val, ""


_DOB_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def validate_dob(raw: str | None) -> tuple[bool, datetime.date | None, str]:
    val = sanitize(raw, 12)
    if not val:
        return False, None, "dob is required (YYYY-MM-DD)."
    if not _DOB_RE.match(val):
        return False, None, "dob must be in YYYY-MM-DD format."
    try:
        d = datetime.date.fromisoformat(val)
        if d > datetime.date.today():
            return False, None, "dob cannot be in the future."
        return True, d, ""
    except ValueError:
        return False, None, "dob is not a valid date."


def validate_gender(raw: str | None) -> tuple[bool, str, str]:
    return validate_role(raw, {"male", "female", "other"})


_PHONE_RE = re.compile(r"^[\d\s\+\-\(\)]{7,20}$")

def validate_contact(raw: str | None) -> tuple[bool, str, str]:
    if not raw:
        return True, "", ""          # optional field
    val = sanitize(raw, 20)
    if not _PHONE_RE.match(val):
        return False, "", "contact_number format is invalid."
    return True, val, ""


# ── Date-range filter ──────────────────────────────────────────────────────

def validate_date(raw: str | None, field: str = "date") -> tuple[bool, datetime.datetime | None, str]:
    if not raw:
        return True, None, ""
    try:
        dt = datetime.datetime.fromisoformat(raw.strip())
        return True, dt, ""
    except ValueError:
        return False, None, f"{field} must be ISO-8601 (e.g. 2026-04-10T00:00:00)."


# ── Pagination ─────────────────────────────────────────────────────────────

def validate_pagination(page_raw, per_page_raw, max_per_page: int = 100) -> tuple[int, int]:
    try:
        page = max(1, int(page_raw or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = min(max_per_page, max(1, int(per_page_raw or 20)))
    except (TypeError, ValueError):
        per_page = 20
    return page, per_page
