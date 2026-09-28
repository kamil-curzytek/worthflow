"""Single local user support today, designed so real multi-user auth can be
added later without changing how accounts/snapshots reference a user.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import User

LOCAL_USER_EMAIL = "local@worthflow.app"
LOCAL_USER_DISPLAY_NAME = "Local User"


def get_or_create_local_user(db: Session) -> User:
    stmt = select(User).where(User.email == LOCAL_USER_EMAIL)
    user = db.scalars(stmt).first()
    if user is not None:
        return user

    user = User(email=LOCAL_USER_EMAIL, display_name=LOCAL_USER_DISPLAY_NAME)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
