"""
patient_routes.py - Patient management Blueprint.

Endpoints:
  GET  /patients            — List all patients (paginated)
  POST /patients            — Create a new patient (admin, doctor)
  GET  /patients/<id>       — Get a single patient
  PUT  /patients/<id>       — Update a patient (admin, doctor)
  DELETE /patients/<id>     — Delete a patient (admin only)
"""

from flask import Blueprint, request, jsonify, g

from models.patient_model import Patient
from models.user_model import User
from utils.db import db
from utils.security import jwt_required, roles_required
from utils.validators import (
    validate_name, validate_dob, validate_gender,
    validate_contact, validate_patient_id, validate_pagination,
)

patient_bp = Blueprint("patients", __name__, url_prefix="/patients")


# ── GET /patients ──────────────────────────────────────────────────────────

@patient_bp.route("", methods=["GET"])
@jwt_required
def list_patients():
    """Return paginated patient list. Accessible by all authenticated roles."""
    page, per_page = validate_pagination(
        request.args.get("page"), request.args.get("per_page")
    )
    search = (request.args.get("search") or "").strip()

    q = Patient.query
    if search:
        q = q.filter(Patient.name.ilike(f"%{search}%"))

    pagination = q.order_by(Patient.patient_id.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Enrich with doctor name
    results = []
    for p in pagination.items:
        d = p.to_dict()
        if p.assigned_doctor:
            doc = db.session.get(User, p.assigned_doctor)
            d["doctor_name"] = doc.username if doc else None
        else:
            d["doctor_name"] = None
        results.append(d)

    return jsonify({
        "total":    pagination.total,
        "page":     pagination.page,
        "pages":    pagination.pages,
        "patients": results,
    }), 200


# ── POST /patients ─────────────────────────────────────────────────────────

@patient_bp.route("", methods=["POST"])
@jwt_required
@roles_required("admin", "doctor")
def create_patient():
    """
    Create a new patient record.
    Body (JSON):
      name, dob (YYYY-MM-DD), gender (male/female/other),
      contact_number (optional), assigned_doctor (int, optional)
    """
    data = request.get_json(silent=True) or {}

    ok, name, err = validate_name(data.get("name"), "name")
    if not ok:
        return jsonify({"error": err}), 400

    ok, dob, err = validate_dob(data.get("dob"))
    if not ok:
        return jsonify({"error": err}), 400

    ok, gender, err = validate_gender(data.get("gender"))
    if not ok:
        return jsonify({"error": err}), 400

    ok, contact, err = validate_contact(data.get("contact_number"))
    if not ok:
        return jsonify({"error": err}), 400

    assigned_doctor = data.get("assigned_doctor")
    if assigned_doctor is not None:
        ok, assigned_doctor, err = validate_patient_id(assigned_doctor)
        if not ok:
            return jsonify({"error": f"assigned_doctor: {err}"}), 400
        doc = db.session.get(User, assigned_doctor)
        if not doc or doc.role != "doctor":
            return jsonify({"error": "assigned_doctor must be an existing user with role=doctor."}), 400

    patient = Patient(
        name=name,
        dob=dob,
        gender=gender,
        contact_number=contact or None,
        assigned_doctor=assigned_doctor,
    )
    db.session.add(patient)
    db.session.commit()

    return jsonify({
        "message": "Patient created successfully.",
        "patient": patient.to_dict(),
    }), 201


# ── GET /patients/<id> ─────────────────────────────────────────────────────

@patient_bp.route("/<int:patient_id>", methods=["GET"])
@jwt_required
def get_patient(patient_id: int):
    """Return a single patient record."""
    patient = db.session.get(Patient, patient_id)
    if not patient:
        return jsonify({"error": "Patient not found."}), 404
    d = patient.to_dict()
    if patient.assigned_doctor:
        doc = db.session.get(User, patient.assigned_doctor)
        d["doctor_name"] = doc.username if doc else None
    return jsonify({"patient": d}), 200


# ── PUT /patients/<id> ─────────────────────────────────────────────────────

@patient_bp.route("/<int:patient_id>", methods=["PUT"])
@jwt_required
@roles_required("admin", "doctor")
def update_patient(patient_id: int):
    """Update patient fields. All fields are optional."""
    patient = db.session.get(Patient, patient_id)
    if not patient:
        return jsonify({"error": "Patient not found."}), 404

    data = request.get_json(silent=True) or {}

    if "name" in data:
        ok, val, err = validate_name(data["name"])
        if not ok:
            return jsonify({"error": err}), 400
        patient.name = val

    if "dob" in data:
        ok, val, err = validate_dob(data["dob"])
        if not ok:
            return jsonify({"error": err}), 400
        patient.dob = val

    if "gender" in data:
        ok, val, err = validate_gender(data["gender"])
        if not ok:
            return jsonify({"error": err}), 400
        patient.gender = val

    if "contact_number" in data:
        ok, val, err = validate_contact(data["contact_number"])
        if not ok:
            return jsonify({"error": err}), 400
        patient.contact_number = val or None

    if "assigned_doctor" in data:
        aid = data["assigned_doctor"]
        if aid is None:
            patient.assigned_doctor = None
        else:
            ok, aid, err = validate_patient_id(aid)
            if not ok:
                return jsonify({"error": f"assigned_doctor: {err}"}), 400
            patient.assigned_doctor = aid

    db.session.commit()
    return jsonify({"message": "Patient updated.", "patient": patient.to_dict()}), 200


# ── DELETE /patients/<id> ──────────────────────────────────────────────────

@patient_bp.route("/<int:patient_id>", methods=["DELETE"])
@jwt_required
@roles_required("admin")
def delete_patient(patient_id: int):
    """Delete a patient (and cascade to associated images/predictions). Admin only."""
    patient = db.session.get(Patient, patient_id)
    if not patient:
        return jsonify({"error": "Patient not found."}), 404

    db.session.delete(patient)
    db.session.commit()
    return jsonify({"message": f"Patient #{patient_id} deleted."}), 200
