"""
Shared login logic with lockout, used by both auth.py (JSON) and
admin_ui.py (HTML) so the lockout behavior can't accidentally exist on
one path and not the other.
"""

from datetime import datetime, timedelta

from .models import db, AdminUser

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def do_login(username: str, password: str):
    user = AdminUser.query.filter_by(username=username).first()
    if user is None:
        return None, "invalid credentials"

    if user.locked_until and datetime.utcnow() < user.locked_until:
        remaining = int((user.locked_until - datetime.utcnow()).total_seconds() / 60) + 1
        return None, f"account locked -- try again in {remaining} minute(s)"

    if not user.check_password(password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
        db.session.commit()
        return None, "invalid credentials"

    user.failed_login_attempts = 0
    user.locked_until = None
    db.session.commit()
    return user, None
