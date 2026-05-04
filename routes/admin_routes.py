"""
admin_routes.py - Admin Dashboard API Blueprint.

All endpoints require JWT + role=admin.

Endpoints:
  GET /admin/dashboard        — Summary stats (event counts, severity breakdown)
  GET /admin/logs             — Paginated audit log with filters
  GET /admin/logs/export      — Download all matching logs as CSV
  GET /admin/users/stats      — User count by role
"""

import csv
import io
import datetime

from flask import Blueprint, request, jsonify, Response, g
from sqlalchemy import func

from models.audit_log_model import AuditLog
from models.user_model import User
from models.image_model import Image
from utils.db import db
from utils.security import jwt_required, roles_required
from utils.validators import validate_date, validate_pagination

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ── Helper: build filtered AuditLog query from request args ───────────────

def _build_log_query():
    q = AuditLog.query

    user_id    = request.args.get("user_id",  type=int)
    action     = request.args.get("action",   type=str)
    severity   = request.args.get("severity", type=str)
    date_from_raw = request.args.get("date_from")
    date_to_raw   = request.args.get("date_to")

    if user_id:
        q = q.filter(AuditLog.performed_by == user_id)

    if action:
        q = q.filter(AuditLog.action == action)

    ok, dt_from, err = validate_date(date_from_raw, "date_from")
    if ok and dt_from:
        q = q.filter(AuditLog.timestamp >= dt_from)

    ok, dt_to, err = validate_date(date_to_raw, "date_to")
    if ok and dt_to:
        q = q.filter(AuditLog.timestamp <= dt_to)

    return q.order_by(AuditLog.timestamp.desc())


# ── GET /admin/dashboard ──────────────────────────────────────────────────

@admin_bp.route("/dashboard", methods=["GET"])
@jwt_required
@roles_required("admin")
def dashboard():
    """Return summary statistics for the admin dashboard."""
    now        = datetime.datetime.utcnow()
    today      = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_24h   = now - datetime.timedelta(hours=24)
    last_7d    = now - datetime.timedelta(days=7)

    total_logs    = AuditLog.query.count()
    today_logs    = AuditLog.query.filter(AuditLog.timestamp >= today).count()
    week_logs     = AuditLog.query.filter(AuditLog.timestamp >= last_7d).count()

    # Distinct active users in last 24 h
    active_users = db.session.query(
        func.count(func.distinct(AuditLog.performed_by))
    ).filter(
        AuditLog.timestamp >= last_24h,
        AuditLog.performed_by.isnot(None),
    ).scalar() or 0

    # Security alerts (integrity failure rows)
    integrity_alerts = AuditLog.query.filter(
        AuditLog.action == "image_integrity_failure"
    ).count()

    # Action breakdown (all time)
    action_rows = db.session.query(
        AuditLog.action,
        func.count(AuditLog.log_id).label("cnt"),
    ).group_by(AuditLog.action).all()

    action_breakdown = {row.action: row.cnt for row in action_rows}

    # Entity counts
    total_users   = User.query.count()
    total_images  = Image.query.count()

    return jsonify({
        "total_logs":        total_logs,
        "today_logs":        today_logs,
        "week_logs":         week_logs,
        "active_users_24h":  active_users,
        "integrity_alerts":  integrity_alerts,
        "total_users":       total_users,
        "total_images":      total_images,
        "action_breakdown":  action_breakdown,
    }), 200


# ── GET /admin/logs ───────────────────────────────────────────────────────

@admin_bp.route("/logs", methods=["GET"])
@jwt_required
@roles_required("admin")
def list_logs():
    """
    Paginated audit log with optional filters.

    Query params:
      user_id     : filter by performing user
      action      : exact action type string
      date_from   : ISO-8601 start datetime
      date_to     : ISO-8601 end datetime
      page        : page number (default 1)
      per_page    : rows per page (max 200, default 50)
    """
    page, per_page = validate_pagination(
        request.args.get("page"), request.args.get("per_page"), max_per_page=200
    )

    query      = _build_log_query()
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    logs = []
    for entry in pagination.items:
        d = entry.to_dict()
        # Attach username if user exists
        if entry.performed_by:
            u = db.session.get(User, entry.performed_by)
            d["username"] = u.username if u else f"user#{entry.performed_by}"
        else:
            d["username"] = "—"
        logs.append(d)

    return jsonify({
        "total":    pagination.total,
        "page":     pagination.page,
        "pages":    pagination.pages,
        "per_page": per_page,
        "logs":     logs,
    }), 200


# ── GET /admin/logs/export ────────────────────────────────────────────────

@admin_bp.route("/logs/export", methods=["GET"])
@jwt_required
@roles_required("admin")
def export_logs():
    """
    Stream all filtered audit log rows as a CSV file download.
    Applies same filters as /admin/logs (no pagination).
    """
    query = _build_log_query().limit(50_000)   # safety cap

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["log_id", "timestamp", "action", "user_id", "username",
                     "target_type", "target_id", "ip_address", "details"])

    for entry in query:
        username = "—"
        if entry.performed_by:
            u = db.session.get(User, entry.performed_by)
            username = u.username if u else f"user#{entry.performed_by}"

        writer.writerow([
            entry.log_id,
            entry.timestamp.isoformat(),
            entry.action,
            entry.performed_by or "",
            username,
            entry.target_type or "",
            entry.target_id or "",
            entry.ip_address or "",
            entry.details or "",
        ])

    buf.seek(0)
    filename = f"audit_log_{datetime.datetime.utcnow():%Y%m%d_%H%M%S}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── GET /admin/users/stats ────────────────────────────────────────────────

@admin_bp.route("/users/stats", methods=["GET"])
@jwt_required
@roles_required("admin")
def user_stats():
    """Return count of users grouped by role."""
    rows = db.session.query(
        User.role,
        func.count(User.user_id).label("count"),
    ).group_by(User.role).all()

    return jsonify({r.role: r.count for r in rows}), 200


# ── GET /admin/action-types ───────────────────────────────────────────────

@admin_bp.route("/action-types", methods=["GET"])
@jwt_required
@roles_required("admin")
def action_types():
    """Return the distinct action types present in the audit log."""
    rows = db.session.query(func.distinct(AuditLog.action)).all()
    return jsonify({"action_types": [r[0] for r in rows]}), 200
