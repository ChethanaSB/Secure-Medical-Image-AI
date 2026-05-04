"""
app.py - Flask application factory and entry point.

Configuration priority (highest → lowest):
  1. Environment variables (recommended for production)
  2. .env file loaded by python-dotenv
  3. Built-in defaults (SQLite + a development secret key)

Run:
  python app.py            # development server
  flask run                # alternatively via Flask CLI
"""

import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Load .env before anything reads os.getenv
load_dotenv()


def create_app() -> Flask:
    """Application factory – creates and configures the Flask app."""
    app = Flask(__name__)

    # Allow all origins in development (lock down to specific domain in production)
    CORS(app, resources={r"/*": {"origins": "*"}},
         supports_credentials=False)
    # ------------------------------------------------------------------
    # Core configuration
    # ------------------------------------------------------------------
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me-in-production")
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "jwt-secret-change-me")

    # Database: default to SQLite in project root; set DATABASE_URL for Postgres
    # PostgreSQL example: postgresql://user:password@localhost:5432/medical_db
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "sqlite:///medical.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Enforce 50 MB hard cap on incoming requests (image uploads)
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

    # ------------------------------------------------------------------
    # Initialise extensions
    # ------------------------------------------------------------------
    # Import models so SQLAlchemy knows about them before create_all()
    from utils.db import init_db
    import models.user_model         # noqa: F401
    import models.patient_model      # noqa: F401
    import models.image_model        # noqa: F401
    import models.audit_log_model    # noqa: F401
    import models.prediction_model   # noqa: F401

    init_db(app)

    # ------------------------------------------------------------------
    # Register blueprints
    # ------------------------------------------------------------------
    from routes.auth_routes import auth_bp
    from routes.image_routes import image_bp
    from routes.admin_routes import admin_bp
    from routes.patient_routes import patient_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(image_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(patient_bp)

    # ------------------------------------------------------------------
    # Health-check endpoint
    # ------------------------------------------------------------------
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "Secure Medical Image API"}), 200

    # ------------------------------------------------------------------
    # Global error handlers
    # ------------------------------------------------------------------
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Endpoint not found."}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed."}), 405

    @app.errorhandler(413)
    def request_too_large(e):
        return jsonify({"error": "File too large. Maximum upload size is 50 MB."}), 413

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"error": "Internal server error."}), 500

    return app


# ------------------------------------------------------------------
# Seed a default admin user so the system is usable out of the box
# ------------------------------------------------------------------
def seed_admin(app: Flask):
    """
    Create a default 'admin' user if no admin exists.
    Credentials are read from ADMIN_USERNAME / ADMIN_PASSWORD env vars
    (defaults: admin / Admin@1234).
    """
    from models.user_model import User
    from utils.db import db
    from utils.security import hash_password

    with app.app_context():
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "Admin@1234")

        existing = User.query.filter_by(username=admin_username).first()
        if not existing:
            admin = User(
                username=admin_username,
                password_hash=hash_password(admin_password),
                role="admin",
            )
            db.session.add(admin)
            db.session.commit()
            print(f"[SEED] Default admin user '{admin_username}' created.")
        else:
            print(f"[SEED] Admin user '{admin_username}' already exists – skipping.")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    flask_app = create_app()
    seed_admin(flask_app)

    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    port = int(os.getenv("PORT", 5000))

    print(f"[APP] Starting Secure Medical Image API on port {port} (debug={debug_mode})")
    flask_app.run(host="0.0.0.0", port=port, debug=debug_mode)
