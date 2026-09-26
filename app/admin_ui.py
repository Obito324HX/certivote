"""
HTML pages for registrars and super_admins -- login, voter lookup,
phone registration/re-bind (including the two-person approval prompt
and time-lock when an election is open), roster import, and the
supervised kiosk voting flow for students with no phone/lost access.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from .models import db, Election
from .auth import require_role_page, current_admin
from . import auth_logic
from . import registrar_logic as logic
from . import voting_logic

admin_ui_bp = Blueprint("admin_ui", __name__, url_prefix="/admin")


@admin_ui_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("admin_login.html")

    user, error = auth_logic.do_login(request.form.get("username", "").strip(),
                                       request.form.get("password", ""))
    if error:
        return render_template("admin_login.html", error=error)

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
    flash(result.get("error") if status != 200 else result.get("message", "Phone number re-bound."))

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


@admin_ui_bp.route("/kiosk/<exam_number>")
@require_role_page("registrar", "super_admin")
def kiosk(exam_number):
    """
    Supervised in-person voting for a student with no phone or lost
    access. The registrar has already checked the student's ID card --
    that in-person check is what stands in for the OTP here.
    """
    voter_result, status = logic.do_lookup(exam_number)
    if status != 200:
        flash(voter_result.get("error"))
        return redirect(url_for("admin_ui.dashboard"))

    from .models import Voter
    voter = Voter.query.filter_by(exam_number=exam_number).first()
    eligible = voting_logic.eligible_open_elections(voter)
    return render_template("admin_kiosk.html", voter=voter, elections=eligible)


@admin_ui_bp.route("/kiosk/<exam_number>/<int:election_id>")
@require_role_page("registrar", "super_admin")
def kiosk_ballot(exam_number, election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        flash("Election not found.")
        return redirect(url_for("admin_ui.kiosk", exam_number=exam_number))
    return render_template("admin_kiosk_ballot.html", exam_number=exam_number, election=election)


@admin_ui_bp.route("/kiosk/<exam_number>/<int:election_id>/cast", methods=["POST"])
@require_role_page("registrar", "super_admin")
def kiosk_cast(exam_number, election_id):
    election = db.session.get(Election, election_id)
    selections = []
    if election:
        for position in election.positions:
            for candidate_id in request.form.getlist(f"position_{position.id}"):
                selections.append({"position_id": position.id, "candidate_id": int(candidate_id)})

    result, status = voting_logic.do_kiosk_cast(current_admin().id, exam_number, election_id, selections)
    flash(result.get("error") if status != 200 else "Vote recorded (supervised).")

    if status != 200:
        return redirect(url_for("admin_ui.kiosk_ballot", exam_number=exam_number, election_id=election_id))
    return redirect(url_for("admin_ui.dashboard"))
