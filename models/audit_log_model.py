"""
audit_log_model.py - SQLAlchemy model for the AUDIT_LOG table.

Every security-sensitive action (upload, download, delete, login, etc.)
is recorded here for forensic traceability.

Columns:
  log_id        Integer, PK, auto-increment
  action        String(50)  — e.g. 'image_upload', 'image_download', 'login'
  performed_by  Integer, FK → user.user_id (nullable — covers unauthenticated events)
  target_type   String(30)  — e.g. 'image', 'user', 'patient'
  target_id     Integer     — PK of the affected record (nullable)
  details       Text        — JSON string with extra context  
  ip_address    String(45)  — IPv4 or IPv6 of the request source
  timestamp     DateTime    — UTC, auto-set on insert
"""

import datetime
from utils.db import db


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    action = db.Column(db.String(50), nullable=False, index=True)

    performed_by = db.Column(
        db.Integer,
        db.ForeignKey("user.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    target_type = db.Column(db.String(30), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)

    # Stores a JSON-encoded dict with additional event-specific data
    details = db.Column(db.Text, nullable=True)

    ip_address = db.Column(db.String(45), nullable=True)

    timestamp = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
        index=True,
    )

    # ── Relationship ──────────────────────────────────────────────────────
    actor = db.relationship("User", backref=db.backref("audit_logs", lazy=True))

    # ── Helpers ───────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "log_id": self.log_id,
            "action": self.action,
            "performed_by": self.performed_by,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.log_id} action={self.action!r} "
            f"by={self.performed_by} at={self.timestamp}>"
        )
