"""
image_model.py - SQLAlchemy model for the IMAGE table.

Columns:
  image_id          Integer, PK, auto-increment
  patient_id        Integer, FK → patient.patient_id
  uploaded_by       Integer, FK → user.user_id
  encrypted_data    LargeBinary (BLOB) — AES-256-CBC ciphertext, NEVER plaintext
  sha256_hash       String(64)         — hex SHA-256 of original plaintext
  iv                String(32)         — hex-encoded 16-byte AES IV
  image_type        String(10)         — 'jpg', 'png', or 'dcm'
  upload_timestamp  DateTime           — UTC, auto-set on insert
"""

import datetime
from utils.db import db


class Image(db.Model):
    __tablename__ = "image"

    image_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patient.patient_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by = db.Column(
        db.Integer,
        db.ForeignKey("user.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Encrypted payload (AES-256-CBC) ──────────────────────────────────
    encrypted_data = db.Column(db.LargeBinary, nullable=False)

    # ── Integrity + decryption metadata ──────────────────────────────────
    sha256_hash = db.Column(db.String(64), nullable=False)
    iv = db.Column(db.String(32), nullable=False)   # hex-encoded 16 bytes

    # ── Classification ────────────────────────────────────────────────────
    image_type = db.Column(
        db.Enum("jpg", "jpeg", "png", "dcm", name="image_type_enum"),
        nullable=False,
    )

    upload_timestamp = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
    )

    # ── Relationships ─────────────────────────────────────────────────────
    patient = db.relationship("Patient", backref=db.backref("images", lazy=True))
    uploader = db.relationship("User", backref=db.backref("uploaded_images", lazy=True))

    # ── Helpers ───────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        """JSON-serialisable representation (never exposes encrypted_data or IV)."""
        return {
            "image_id": self.image_id,
            "patient_id": self.patient_id,
            "uploaded_by": self.uploaded_by,
            "sha256_hash": self.sha256_hash,
            "image_type": self.image_type,
            "upload_timestamp": self.upload_timestamp.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"<Image id={self.image_id} patient={self.patient_id} "
            f"type={self.image_type!r}>"
        )
