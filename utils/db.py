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
        try:
            db.create_all()
            print("[DB] Tables created / verified successfully.")

            # ── Migrate: add supabase_id column if missing (SQLite only) ─
            _ensure_supabase_id_column(app)
        except Exception as exc:
            log.error(
                "[DB] Could not connect to database on startup: %s\n"
                "     Make sure DATABASE_URL is set correctly in Render "
                "Environment Variables and that the Supabase Session Pooler "
                "URL is used (IPv4 compatible, port 5432 via pooler).",
                exc,
            )


def _ensure_supabase_id_column(app):
    """Add 'supabase_id' column to 'users' table if it doesn't exist yet.
    Uses SQLAlchemy inspect() so it works on both SQLite and PostgreSQL.
    """
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        # db.create_all() already handles column creation on PostgreSQL,
        # so this migration is only needed for existing SQLite databases.
        dialect = db.engine.dialect.name  # 'sqlite' or 'postgresql'
        if dialect != "sqlite":
            print("[DB] Skipping SQLite migration on PostgreSQL — db.create_all() handles schema.")
            return

        columns = [col["name"] for col in inspector.get_columns("users")]
        if "supabase_id" not in columns:
            with db.engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN supabase_id VARCHAR(255)"
                ))
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_supabase_id ON users(supabase_id)"
                ))
                conn.commit()
            print("[DB] Added 'supabase_id' column to users table.")
        else:
            print("[DB] 'supabase_id' column already exists.")
    except Exception as exc:
        log.warning("Could not check/add supabase_id column: %s", exc)
