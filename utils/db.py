"""
db.py - Database initialization and configuration using SQLAlchemy.
Supports both SQLite (default) and PostgreSQL via DATABASE_URL env variable.
"""

import os
from flask_sqlalchemy import SQLAlchemy

# Shared SQLAlchemy instance - imported by models and app
db = SQLAlchemy()


def init_db(app):
    """
    Bind the SQLAlchemy instance to the Flask app and create all tables.
    Call this from app.py after configuring the app.
    """
    db.init_app(app)
    with app.app_context():
        db.create_all()
        print("[DB] Tables created / verified successfully.")
