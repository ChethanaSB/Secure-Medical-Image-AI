"""
user_model.py - SQLAlchemy model for the USER table.

Columns:
  user_id       Integer, primary key, auto-increment
  username      String(80), unique, not null
  password_hash String(255), not null  — stored as bcrypt hash
  role          Enum('admin', 'doctor', 'radiologist'), not null
  created_at    DateTime, default = UTC now
"""

import datetime
from utils.db import db


class User(db.Model):
    __tablename__ = "user"

    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.Enum("admin", "doctor", "radiologist", name="user_role_enum"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------
    # One doctor can be assigned many patients
    patients = db.relationship(
        "Patient",
        backref="doctor",
        lazy=True,
        foreign_keys="Patient.assigned_doctor",
    )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation (no password_hash)."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<User id={self.user_id} username={self.username!r} role={self.role!r}>"
