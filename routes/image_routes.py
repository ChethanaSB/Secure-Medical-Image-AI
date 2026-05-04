"""
image_routes.py - Secure medical image management Blueprint.

Endpoints:
  POST   /images/upload               — Upload + encrypt a medical image
  GET    /images/view/<image_id>       — Decrypt, verify, analyse with AI, return report
  GET    /images/<image_id>/info       — Retrieve image metadata (no binary)
  GET    /images/patient/<pid>         — List all images for a patient
  GET    /images/<image_id>/verify     — Verify SHA-256 integrity of stored image
  GET    /images/audit                 — Admin: view upload audit log

Access control:
  • All endpoints require JWT authentication.
  • Upload / view: admin, doctor, radiologist
  • Patient listing / info: admin, doctor, radiologist
  • Audit log: admin only
"""

import json
import os
import base64
import logging

from flask import Blueprint, request, jsonify, g

from models.image_model import Image
from models.audit_log_model import AuditLog
from models.patient_model import Patient
from models.prediction_model import Prediction
from utils.db import db
from utils.security import jwt_required, roles_required, get_client_ip
from utils.encryption import compute_sha256, encrypt_image, verify_integrity, decrypt_image
from utils.ai_services import analyze_with_huggingface, generate_clinical_report

logger = logging.getLogger(__name__)

image_bp = Blueprint("images", __name__, url_prefix="/images")

# ---------------------------------------------------------------------------
# Allowed file types and their canonical name
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {
    "jpg": "jpg",
    "jpeg": "jpeg",
    "png": "png",
    "dcm": "dcm",
}

# 50 MB hard cap on upload size
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _allowed_file(filename: str) -> tuple[bool, str]:
    """
    Validate filename extension.
    Returns (ok: bool, ext: str).
    """
    if "." not in filename:
        return False, ""
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext in ALLOWED_EXTENSIONS:
        return True, ALLOWED_EXTENSIONS[ext]
    return False, ext


def _write_audit(
    action: str,
    user_id: int | None,
    target_type: str,
    target_id: int | None,
    details: dict,
    ip: str,
):
    """Persist a single audit log row (does NOT commit — caller must commit)."""
    log = AuditLog(
        action=action,
        performed_by=user_id,
        target_type=target_type,
        target_id=target_id,
        details=json.dumps(details),
        ip_address=ip,
    )
    db.session.add(log)


# ---------------------------------------------------------------------------
# POST /images/upload
# ---------------------------------------------------------------------------
@image_bp.route("/upload", methods=["POST"])
@jwt_required
@roles_required("admin", "doctor", "radiologist")
def upload_image():
    """
    Accept a medical image, encrypt it with AES-256-CBC, and persist only the
    ciphertext, IV, and SHA-256 hash.  Plaintext is NEVER written to disk or DB.

    Form fields:
      file        — multipart file (jpg / jpeg / png / dcm)
      patient_id  — integer ID of the patient this image belongs to

    Returns JSON with image metadata on success.
    """
    ip = get_client_ip()
    user_id: int = g.current_user["id"]

    # ── 1. Validate form/file presence ───────────────────────────────────
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request."}), 400

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    patient_id_raw = request.form.get("patient_id", "").strip()
    if not patient_id_raw or not patient_id_raw.isdigit():
        return jsonify({"error": "patient_id (integer) is required."}), 400
    patient_id = int(patient_id_raw)

    # ── 2. Validate file extension ────────────────────────────────────────
    ok, ext = _allowed_file(file.filename)
    if not ok:
        return jsonify({
            "error": f"File type '{ext}' is not allowed. "
                     f"Accepted: jpg, jpeg, png, dcm."
        }), 415

    # ── 3. Read binary — never write to disk ─────────────────────────────
    raw_bytes = file.read()

    if len(raw_bytes) == 0:
        return jsonify({"error": "Uploaded file is empty."}), 400

    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        return jsonify({
            "error": f"File exceeds maximum allowed size of "
                     f"{MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
        }), 413

    # ── 4. Verify the patient exists ──────────────────────────────────────
    patient = db.session.get(Patient, patient_id)
    if not patient:
        return jsonify({"error": f"Patient with id={patient_id} not found."}), 404

    # ── 5. Compute SHA-256 of plaintext (before encryption) ──────────────
    sha256_hex = compute_sha256(raw_bytes)

    # ── 6. Encrypt with AES-256-CBC ───────────────────────────────────────
    try:
        ciphertext, iv_bytes = encrypt_image(raw_bytes)
    except RuntimeError as exc:
        # AES_KEY misconfiguration — log but hide details from client
        _write_audit(
            "image_upload_failed",
            user_id,
            "image",
            None,
            {"reason": "encryption_key_error", "patient_id": patient_id},
            ip,
        )
        db.session.commit()
        return jsonify({"error": "Server encryption configuration error."}), 500

    # Erase plaintext from memory immediately (best-effort in CPython)
    del raw_bytes

    iv_hex = iv_bytes.hex()   # store as 32-char hex string

    # ── 7. Persist to database ────────────────────────────────────────────
    image_record = Image(
        patient_id=patient_id,
        uploaded_by=user_id,
        encrypted_data=ciphertext,
        sha256_hash=sha256_hex,
        iv=iv_hex,
        image_type=ext,
    )
    db.session.add(image_record)
    db.session.flush()   # get image_id before commit

    # ── 8. Audit log ──────────────────────────────────────────────────────
    _write_audit(
        "image_upload",
        user_id,
        "image",
        image_record.image_id,
        {
            "patient_id": patient_id,
            "image_type": ext,
            "sha256_hash": sha256_hex,
            "file_size_bytes": len(ciphertext),
        },
        ip,
    )

    db.session.commit()

    return jsonify({
        "message": "Image uploaded and encrypted successfully.",
        "image": image_record.to_dict(),
    }), 201


# ---------------------------------------------------------------------------
# GET /images/<image_id>/info
# ---------------------------------------------------------------------------
@image_bp.route("/<int:image_id>/info", methods=["GET"])
@jwt_required
@roles_required("admin", "doctor", "radiologist")
def image_info(image_id: int):
    """Return metadata for a single image (does NOT return binary or IV)."""
    image = db.session.get(Image, image_id)
    if not image:
        return jsonify({"error": "Image not found."}), 404
    return jsonify({"image": image.to_dict()}), 200


# ---------------------------------------------------------------------------
# GET /images/patient/<patient_id>
# ---------------------------------------------------------------------------
@image_bp.route("/patient/<int:patient_id>", methods=["GET"])
@jwt_required
@roles_required("admin", "doctor", "radiologist")
def list_patient_images(patient_id: int):
    """Return a paginated list of image metadata for the given patient."""
    patient = db.session.get(Patient, patient_id)
    if not patient:
        return jsonify({"error": f"Patient with id={patient_id} not found."}), 404

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    pagination = (
        Image.query
        .filter_by(patient_id=patient_id)
        .order_by(Image.upload_timestamp.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify({
        "patient_id": patient_id,
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
        "images": [img.to_dict() for img in pagination.items],
    }), 200


# ---------------------------------------------------------------------------
# GET /images/<image_id>/verify
# ---------------------------------------------------------------------------
@image_bp.route("/<int:image_id>/verify", methods=["GET"])
@jwt_required
@roles_required("admin", "doctor", "radiologist")
def verify_image(image_id: int):
    """
    Decrypt the stored ciphertext and re-compute its SHA-256 hash.
    Returns whether the hash matches the stored value (tamper detection).
    """
    from utils.encryption import decrypt_image

    image = db.session.get(Image, image_id)
    if not image:
        return jsonify({"error": "Image not found."}), 404

    try:
        iv_bytes = bytes.fromhex(image.iv)
        plaintext = decrypt_image(image.encrypted_data, iv_bytes)
        intact = verify_integrity(image.sha256_hash, plaintext)
    except Exception:
        return jsonify({
            "image_id": image_id,
            "integrity_ok": False,
            "detail": "Decryption or hash verification failed.",
        }), 500
    finally:
        # Best-effort wipe
        try:
            del plaintext
        except Exception:
            pass

    return jsonify({
        "image_id": image_id,
        "integrity_ok": intact,
        "detail": "SHA-256 hash matches." if intact else "HASH MISMATCH — data may be corrupt or tampered.",
    }), 200


# ---------------------------------------------------------------------------
# GET /images/audit  (admin only)
# ---------------------------------------------------------------------------
@image_bp.route("/audit", methods=["GET"])
@jwt_required
@roles_required("admin")
def audit_log():
    """Return a paginated audit log, optionally filtered by action or user."""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    filter_action = request.args.get("action")
    filter_user = request.args.get("user_id", type=int)

    query = AuditLog.query.order_by(AuditLog.timestamp.desc())
    if filter_action:
        query = query.filter(AuditLog.action == filter_action)
    if filter_user:
        query = query.filter(AuditLog.performed_by == filter_user)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
        "logs": [log.to_dict() for log in pagination.items],
    }), 200


# ---------------------------------------------------------------------------
# GET /images/view/<image_id>  — Full AI retrieval pipeline
# ---------------------------------------------------------------------------
@image_bp.route("/view/<int:image_id>", methods=["GET"])
@jwt_required
@roles_required("admin", "doctor", "radiologist")
def view_image(image_id: int):
    """
    Full image retrieval + AI analysis pipeline:
      1. Fetch encrypted image from DB
      2. Decrypt with AES-256-CBC
      3. Verify SHA-256 integrity
      4. If mismatch → log SECURITY ALERT, return 409
      5. Convert plaintext to base64 for response
      6. Analyse with HuggingFace chest X-ray model
      7. Generate structured clinical report via Claude
      8. Store prediction in DB
      9. Write image_view audit log
     10. Return image (base64) + prediction + report

    Query params:
      force_reanalyze=true  — skip cached prediction and re-call AI APIs
    """
    ip = get_client_ip()
    user_id: int = g.current_user["id"]
    force_reanalyze: bool = (
        request.args.get("force_reanalyze", "false").lower() == "true"
    )

    # ── 1. Fetch image record ─────────────────────────────────────────────
    image = db.session.get(Image, image_id)
    if not image:
        return jsonify({"error": "Image not found."}), 404

    # ── 2. Decrypt ────────────────────────────────────────────────────────
    try:
        iv_bytes = bytes.fromhex(image.iv)
        plaintext = decrypt_image(image.encrypted_data, iv_bytes)
    except Exception as exc:
        logger.error("Decryption failed for image %s: %s", image_id, exc)
        _write_audit(
            "image_decrypt_failure", user_id, "image", image_id,
            {"error": str(exc)}, ip,
        )
        db.session.commit()
        return jsonify({"error": "Failed to decrypt image."}), 500

    # ── 3. Verify SHA-256 integrity ───────────────────────────────────────
    intact = verify_integrity(image.sha256_hash, plaintext)

    if not intact:
        # ── 4. Integrity failure → security alert ─────────────────────────
        logger.critical(
            "SECURITY ALERT: SHA-256 hash mismatch on image_id=%s (user=%s ip=%s)",
            image_id, user_id, ip,
        )
        _write_audit(
            "image_integrity_failure",
            user_id,
            "image",
            image_id,
            {
                "severity": "HIGH",
                "stored_hash": image.sha256_hash,
                "alert": (
                    "SECURITY: SHA-256 hash mismatch detected during retrieval. "
                    "Possible tampering or data corruption."
                ),
            },
            ip,
        )
        db.session.commit()
        del plaintext
        return jsonify({
            "error": "Integrity Failure",
            "detail": (
                "SHA-256 hash mismatch. The image data may be corrupt or has "
                "been tampered with. A security alert has been logged."
            ),
            "image_id": image_id,
        }), 409

    # ── 5. Encode plaintext to base64 for the response ────────────────────
    image_base64 = base64.b64encode(plaintext).decode("utf-8")

    # ── 6 & 7. AI analysis — use cached prediction unless force_reanalyze ─
    existing_pred: Prediction | None = None
    if not force_reanalyze:
        existing_pred = (
            Prediction.query
            .filter_by(image_id=image_id)
            .order_by(Prediction.created_at.desc())
            .first()
        )

    if existing_pred:
        # Return previously stored prediction (saves AI API cost)
        label = existing_pred.label
        confidence = existing_pred.confidence
        report_text = existing_pred.report or ""
        prediction_dict = existing_pred.to_dict()
        is_cached = True
    else:
        # ── 6. HuggingFace analysis ───────────────────────────────────────
        hf_error: str | None = None
        label = "Analysis unavailable"
        confidence = 0.0
        model_used = os.getenv("HF_MODEL_ID",
            "nickmuchi/vit-base-patch16-224-finetuned-chest-xray-pneumonia")

        try:
            hf_result = analyze_with_huggingface(plaintext, image.image_type)
            label = hf_result["label"]
            confidence = hf_result["confidence"]
            model_used = hf_result["model_used"]
        except Exception as exc:
            hf_error = str(exc)
            logger.error("HuggingFace analysis failed for image %s: %s",
                         image_id, exc)
            _write_audit(
                "hf_analysis_failure", user_id, "image", image_id,
                {"error": hf_error, "image_type": image.image_type}, ip,
            )

        # ── 7. Gemini clinical report ─────────────────────────────────────
        gemini_error: str | None = None
        report_text = ""

        try:
            report_text = generate_clinical_report(
                label, confidence, image.image_type
            )
        except Exception as exc:
            gemini_error = str(exc)
            logger.error("Gemini report generation failed for image %s: %s",
                         image_id, exc)
            report_text = (
                f"[Clinical report generation failed: {gemini_error}. "
                f"AI label: {label} ({confidence*100:.1f}% confidence)]"
            )
            _write_audit(
                "gemini_report_failure", user_id, "image", image_id,
                {"error": gemini_error}, ip,
            )

        # ── 8. Persist prediction ─────────────────────────────────────────
        new_pred = Prediction(
            image_id=image_id,
            patient_id=image.patient_id,
            label=label,
            confidence=confidence,
            report=report_text,
            model_used=model_used,
        )
        db.session.add(new_pred)
        db.session.flush()   # obtain prediction_id before commit
        prediction_dict = new_pred.to_dict()
        is_cached = False

    # ── 9. Audit log — successful view ────────────────────────────────────
    _write_audit(
        "image_view",
        user_id,
        "image",
        image_id,
        {
            "patient_id": image.patient_id,
            "image_type": image.image_type,
            "integrity_verified": True,
            "prediction_label": label,
            "prediction_confidence": round(confidence, 4),
            "cached_prediction": is_cached,
        },
        ip,
    )
    db.session.commit()

    # Best-effort wipe of decrypted bytes now that base64 copy exists
    del plaintext

    # ── 10. Return response ───────────────────────────────────────────────
    return jsonify({
        "image_id": image_id,
        "patient_id": image.patient_id,
        "image_type": image.image_type,
        "integrity_verified": True,
        "image_base64": image_base64,
        "prediction": prediction_dict,
        "clinical_report": report_text,
        "cached_prediction": is_cached,
    }), 200
