"""
HTML pages for registrars and super_admins -- login, voter lookup,
phone registration/re-bind (including the two-person approval prompt
when an election is open), and roster import.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from .models import AdminUser
from .auth import require_role_page, current_admin
from . import registrar_logic as logic

admin_ui_bp = Blueprint("admin_ui", __name__, url_prefix="/admin")


@admin_ui_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("admin_login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    user = AdminUser.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return render_template("admin_login.html", error="Invalid credentials.")

    session["admin_user_id"] = user.id
    session["admin_role"] = user.role.value
    return redirect(url_for("admin_ui.dashboard"))


@admin_ui_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("admin_ui.login"))


@admin_ui_bp.route("/")
@require_role_page("registrar", "super_admin")
def dashboard():
    return render_template("admin_dashboard.html", admin=current_admin(),
                            election_open=logic.any_election_open())


@admin_ui_bp.route("/lookup", methods=["POST"])
@require_role_page("registrar", "super_admin")
def lookup():
    exam_number = request.form.get("exam_number", "").strip()
    result, status = logic.do_lookup(exam_number)

    if status != 200:
        flash(result.get("error"))
        return redirect(url_for("admin_ui.dashboard"))

    return render_template("admin_dashboard.html", admin=current_admin(),
                            election_open=logic.any_election_open(), voter=result)


@admin_ui_bp.route("/register", methods=["POST"])
@require_role_page("registrar", "super_admin")
def register():
    exam_number = request.form.get("exam_number", "").strip()
    phone_number = request.form.get("phone_number", "").strip()

    result, status = logic.do_register(current_admin().id, exam_number, phone_number)
    flash(result.get("error") if status != 200 else "Phone number registered.")

    voter, _ = logic.do_lookup(exam_number)
    return render_template("admin_dashboard.html", admin=current_admin(),
                            election_open=logic.any_election_open(), voter=voter)


@admin_ui_bp.route("/rebind", methods=["POST"])
@require_role_page("registrar", "super_admin")
def rebind():
    exam_number = request.form.get("exam_number", "").strip()
    new_phone_number = request.form.get("new_phone_number", "").strip()
    approver_username = request.form.get("approver_username", "").strip() or None
    approver_password = request.form.get("approver_password") or None

    result, status = logic.do_rebind(
        current_admin().id, exam_number, new_phone_number, approver_username, approver_password
    )
    flash(result.get("error") if status != 200 else "Phone number re-bound.")

    voter, _ = logic.do_lookup(exam_number)
    return render_template("admin_dashboard.html", admin=current_admin(),
                            election_open=logic.any_election_open(), voter=voter)


@admin_ui_bp.route("/import", methods=["POST"])
@require_role_page("super_admin")
def import_roster():
    if "file" not in request.files or request.files["file"].filename == "":
        flash("No file selected.")
        return redirect(url_for("admin_ui.dashboard"))

    result, status = logic.do_import_roster(request.files["file"])
    if status != 200:
        flash(result.get("error"))
    else:
        flash(f"Roster imported: {result['created']} created, {result['updated']} updated.")

    return redirect(url_for("admin_ui.dashboard"))
