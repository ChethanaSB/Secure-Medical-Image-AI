"""
patient_model.py - SQLAlchemy model for the PATIENT table.

Columns:
  patient_id      Integer, primary key, auto-increment
  name            String(120), not null
  dob             Date, not null
  gender          Enum('male', 'female', 'other'), not null
  contact_number  String(20)
  assigned_doctor Integer, FK → user.user_id (nullable — patient may be unassigned)
"""

from utils.db import db


class Patient(db.Model):
    __tablename__ = "patient"

    patient_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(120), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    gender = db.Column(
        db.Enum("male", "female", "other", name="patient_gender_enum"),
        nullable=False,
    )
    contact_number = db.Column(db.String(20), nullable=True)
    assigned_doctor = db.Column(
        db.Integer,
        db.ForeignKey("user.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation."""
        return {
            "patient_id": self.patient_id,
            "name": self.name,
            "dob": self.dob.isoformat() if self.dob else None,
            "gender": self.gender,
            "contact_number": self.contact_number,
            "assigned_doctor": self.assigned_doctor,
        }

    def __repr__(self) -> str:
        return f"<Patient id={self.patient_id} name={self.name!r}>"
