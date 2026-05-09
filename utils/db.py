"""
db.py - Database initialization and configuration using SQLAlchemy.
Supports both SQLite (default) and PostgreSQL via DATABASE_URL env variable.
"""

import os
import logging
from flask_sqlalchemy import SQLAlchemy

log = logging.getLogger(__name__)

# Shared SQLAlchemy instance - imported by models and app
db = SQLAlchemy()


def init_db(app):
    """
    Bind the SQLAlchemy instance to the Flask app and create all tables.
    Also handles schema migrations for the supabase_id column.
    Call this from app.py after configuring the app.
    """
    db.init_app(app)
    with app.app_context():
        db.create_all()
        print("[DB] Tables created / verified successfully.")

        # ── Migrate: add supabase_id column if missing (SQLite) ──────────
        _ensure_supabase_id_column(app)


def _ensure_supabase_id_column(app):
    """Add 'supabase_id' column to 'user' table if it doesn't exist yet."""
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            # Check if column exists
            result = conn.execute(text("PRAGMA table_info(user)"))
            columns = [row[1] for row in result.fetchall()]

            if "supabase_id" not in columns:
                # SQLite doesn't support UNIQUE in ALTER TABLE ADD COLUMN
                conn.execute(text(
                    "ALTER TABLE user ADD COLUMN supabase_id VARCHAR(255)"
                ))
                # Create unique index separately
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_supabase_id ON user(supabase_id)"
                ))
                conn.commit()
                print("[DB] Added 'supabase_id' column to user table.")
            else:
                print("[DB] 'supabase_id' column already exists.")
    except Exception as exc:
        log.warning("Could not check/add supabase_id column: %s", exc)
