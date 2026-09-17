"""
JSON API for the voting flow. All actual logic lives in voting_logic.py
so the HTML voter pages (voter_ui.py) can call the exact same functions.
"""

from flask import Blueprint, request, jsonify

from . import voting_logic as logic

voting_bp = Blueprint("voting", __name__, url_prefix="/vote")


@voting_bp.route("/request-otp", methods=["POST"])
def request_otp():
    data = request.get_json(force=True)
    result, status = logic.do_request_otp(data.get("exam_number", "").strip(), data.get("election_id"))
    return jsonify(result), status


@voting_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json(force=True)
    result, status = logic.do_verify_otp(
        data.get("exam_number", "").strip(), data.get("election_id"), data.get("otp", "").strip()
    )
    return jsonify(result), status


@voting_bp.route("/cast", methods=["POST"])
def cast_ballot():
    data = request.get_json(force=True)
    result, status = logic.do_cast_ballot(data.get("voting_session_token", ""), data.get("selections", []))
    return jsonify(result), status
