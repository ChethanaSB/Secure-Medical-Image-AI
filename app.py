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
load_dotenv(override=True)


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
    # Serve Frontend Static Files
    # ------------------------------------------------------------------
    from flask import send_from_directory

    @app.route("/")
    def serve_index():
        return send_from_directory("frontend", "index.html")

    @app.route("/<path:path>")
    def serve_static(path):
        import os
        # If the path exists in the frontend folder, serve it
        if os.path.exists(os.path.join("frontend", path)):
            return send_from_directory("frontend", path)
        # Otherwise, fall back to index.html (useful for SPA routing if needed)
        return send_from_directory("frontend", "index.html")

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
def seed_database(app: Flask):
    """
    Seeds the database with required dummy data on startup.
    """
    from models.user_model import User
    from models.patient_model import Patient
    from utils.db import db
    from datetime import date

    with app.app_context():
        # Admin check
        existing_admin = User.query.filter_by(role="admin").first()
        if not existing_admin:
            print("[SEED] No local admin user yet. Register an admin via the web UI")
            print("       and they will be auto-synced on first Supabase login.")
        else:
            print(f"[SEED] Admin user '{existing_admin.username}' exists locally.")
        
        # Patient seed
        if not Patient.query.first():
            print("[SEED] Adding dummy patients for testing...")
            p1 = Patient(name="John Doe", dob=date(1985, 4, 12), gender="male", contact_number="555-0101")
            p2 = Patient(name="Jane Smith", dob=date(1992, 8, 23), gender="female", contact_number="555-0202")
            p3 = Patient(name="Robert Johnson", dob=date(1978, 11, 5), gender="male", contact_number="555-0303")
            db.session.add_all([p1, p2, p3])
            db.session.commit()
            print("[SEED] 3 dummy patients added successfully.")

# ------------------------------------------------------------------
# Entry point / Gunicorn integration
# ------------------------------------------------------------------
# This global 'app' object is used by gunicorn (e.g. gunicorn app:app)
app = create_app()

# Run database seed on startup (for both local and Render environments)
try:
    seed_database(app)
except Exception as e:
    print(f"[SEED] Error seeding database: {e}")

if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    port = int(os.getenv("PORT", 5000))

    print(f"[APP] Starting Secure Medical Image API on port {port} (debug={debug_mode})")
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
