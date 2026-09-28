from contextlib import contextmanager

from app.database.session import SessionLocal


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
