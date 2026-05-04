"""
audit.py - Shared audit-logging helper.

Usage (inside a route, before db.session.commit()):
    from utils.audit import write_audit
    write_audit("login_success", user_id=1, target_type="user",
                target_id=1, details={"username": "admin"}, ip="127.0.0.1")
    db.session.commit()

Action-type constants are also exported so all routes use consistent names.
"""

import json
import logging

from models.audit_log_model import AuditLog
from utils.db import db

log = logging.getLogger(__name__)

# ── Action-type constants ──────────────────────────────────────────────────
LOGIN_SUCCESS             = "login_success"
LOGIN_FAILED              = "login_failed"
LOGIN_LOCKED              = "login_locked"
USER_REGISTERED           = "user_registered"
USER_DELETED              = "user_deleted"
IMAGE_UPLOAD              = "image_upload"
IMAGE_UPLOAD_FAILED       = "image_upload_failed"
IMAGE_VIEW                = "image_view"
IMAGE_DECRYPT_FAILURE     = "image_decrypt_failure"
IMAGE_INTEGRITY_FAILURE   = "image_integrity_failure"
PREDICTION_CREATED        = "prediction_created"
HF_ANALYSIS_FAILURE       = "hf_analysis_failure"
GEMINI_REPORT_FAILURE     = "gemini_report_failure"
PATIENT_CREATED           = "patient_created"
PATIENT_UPDATED           = "patient_updated"
PATIENT_DELETED           = "patient_deleted"

# Severity map (used by the admin dashboard to colour-code rows)
SEVERITY: dict[str, str] = {
    IMAGE_INTEGRITY_FAILURE: "critical",
    IMAGE_DECRYPT_FAILURE:   "high",
    LOGIN_LOCKED:            "high",
    LOGIN_FAILED:            "medium",
    HF_ANALYSIS_FAILURE:     "medium",
    GEMINI_REPORT_FAILURE:   "medium",
    IMAGE_UPLOAD_FAILED:     "low",
}


def write_audit(
    action: str,
    user_id: int | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    details: dict | None = None,
    ip: str | None = None,
) -> None:
    """
    Append an AuditLog row to the current DB session.
    Does NOT call db.session.commit() — the caller is responsible for that.

    Args:
        action      : One of the ACTION_* constants above.
        user_id     : ID of the acting user (performed_by FK).
        target_type : e.g. "image", "user", "patient".
        target_id   : PK of the target record.
        details     : Arbitrary dict serialised to JSON for context.
        ip          : Client IP address.
    """
    severity = SEVERITY.get(action, "info")
    payload = details or {}
    payload["severity"] = severity

    try:
        entry = AuditLog(
            action=action,
            performed_by=user_id,
            target_type=target_type,
            target_id=target_id,
            details=json.dumps(payload),
            ip_address=ip,
        )
        db.session.add(entry)
    except Exception as exc:          # Never let audit failure crash the request
        log.error("Audit write failed for action=%s: %s", action, exc)
