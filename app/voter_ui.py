"""
Voter-facing HTML pages. Deliberately plain server-rendered templates,
no JS framework -- per the low-bandwidth requirement, this needs to load
fast on a slow connection. Flask's signed session cookie carries the
voter's exam_number/election_id/voting_session_token between steps so
nothing sensitive sits in the URL.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from .models import db, Voter, Election
from . import voting_logic as logic

voter_ui_bp = Blueprint("voter_ui", __name__, url_prefix="/v")


@voter_ui_bp.route("/")
def index():
    if session.get("exam_number"):
        return redirect(url_for("voter_ui.elections"))
    return render_template("start.html")


@voter_ui_bp.route("/start", methods=["POST"])
def start():
    exam_number = request.form.get("exam_number", "").strip()
    voter = Voter.query.filter_by(exam_number=exam_number).first()
    if voter is None:
        return render_template("start.html", error="Exam number not found.")

    session.clear()
    session["exam_number"] = exam_number
    return redirect(url_for("voter_ui.elections"))


@voter_ui_bp.route("/elections")
def elections():
    exam_number = session.get("exam_number")
    if not exam_number:
        return redirect(url_for("voter_ui.index"))

    voter = Voter.query.filter_by(exam_number=exam_number).first()
    if voter is None:
        session.clear()
        return redirect(url_for("voter_ui.index"))

    eligible = logic.eligible_open_elections(voter)
    return render_template("elections.html", voter=voter, elections=eligible)


@voter_ui_bp.route("/request-otp", methods=["POST"])
def request_otp():
    exam_number = session.get("exam_number")
    election_id = int(request.form.get("election_id"))
    if not exam_number:
        return redirect(url_for("voter_ui.index"))

    result, status = logic.do_request_otp(exam_number, election_id)
    session["election_id"] = election_id

    if status != 200:
        flash(result.get("error", "Could not send OTP."))
        return redirect(url_for("voter_ui.elections"))

    return render_template("otp.html", info="A verification code was sent to your registered phone.",
                            election_id=election_id)


@voter_ui_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    exam_number = session.get("exam_number")
    election_id = session.get("election_id")
    otp = request.form.get("otp", "").strip()
    if not exam_number or not election_id:
        return redirect(url_for("voter_ui.index"))

    result, status = logic.do_verify_otp(exam_number, election_id, otp)
    if status != 200:
        return render_template("otp.html", error=result.get("error"), election_id=election_id)

    session["voting_session_token"] = result["voting_session_token"]
    return redirect(url_for("voter_ui.ballot"))


@voter_ui_bp.route("/ballot")
def ballot():
    election_id = session.get("election_id")
    if not election_id or not session.get("voting_session_token"):
        return redirect(url_for("voter_ui.index"))

    election = db.session.get(Election, election_id)
    if election is None:
        session.clear()
        return redirect(url_for("voter_ui.index"))

    return render_template("ballot.html", election=election)


@voter_ui_bp.route("/cast", methods=["POST"])
def cast():
    token = session.get("voting_session_token")
    election_id = session.get("election_id")
    if not token or not election_id:
        return redirect(url_for("voter_ui.index"))

    election = db.session.get(Election, election_id)
    selections = []
    for position in election.positions:
        candidate_id = request.form.get(f"position_{position.id}")
        if candidate_id:
            selections.append({"position_id": position.id, "candidate_id": int(candidate_id)})

    result, status = logic.do_cast_ballot(token, selections)
    session.clear()

    if status != 200:
        return render_template("confirmation.html", ok=False, error=result.get("error"))
    return render_template("confirmation.html", ok=True)
