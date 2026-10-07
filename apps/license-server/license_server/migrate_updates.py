"""Add the release catalog without recreating or changing existing license tables.

Run with the production DATABASE_URL: python -m license_server.migrate_updates
"""
from .db import engine
from .updates import WindowsRelease

if __name__ == "__main__":
    WindowsRelease.__table__.create(bind=engine, checkfirst=True)
    print("Windows release catalog is ready")
