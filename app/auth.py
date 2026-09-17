"""
Session-based login for admin/registrar/observer accounts.
"""

from functools import wraps

from flask import Blueprint, request, session, jsonify, redirect, url_for, flash

from .models import db, AdminUser, AdminRole

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    username = data.get("username", "")
    password = data.get("password", "")

    user = AdminUser.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return jsonify({"error": "invalid credentials"}), 401

    session["admin_user_id"] = user.id
    session["admin_role"] = user.role.value
    return jsonify({"username": user.username, "role": user.role.value})


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


def require_role(*allowed_roles: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "admin_user_id" not in session:
                return jsonify({"error": "login required"}), 401
            if session.get("admin_role") not in allowed_roles:
                return jsonify({"error": "not authorized for this action"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def require_role_page(*allowed_roles: str):
    """
    Same check as require_role, but for HTML pages: redirects to the
    admin login page with a flash message instead of returning JSON.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "admin_user_id" not in session:
                flash("Please log in.")
                return redirect(url_for("admin_ui.login"))
            if session.get("admin_role") not in allowed_roles:
                flash("You are not authorized to do that.")
                return redirect(url_for("admin_ui.dashboard"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def current_admin() -> AdminUser:
    return db.session.get(AdminUser, session["admin_user_id"])
