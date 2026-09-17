"""
Post-election audit (authenticated). Public, no-login results/turnout
pages live in public_ui.py and reuse the same results_logic functions.
"""

from flask import Blueprint, jsonify

from .models import db, Election, ElectionStatus
from .auth import require_role
from . import results_logic as logic

results_bp = Blueprint("results", __name__, url_prefix="/elections")


@results_bp.route("/<int:election_id>/audit", methods=["GET"])
@require_role("registrar", "super_admin", "observer")
def audit(election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        return jsonify({"error": "election not found"}), 404
    if election.status not in (ElectionStatus.CLOSED, ElectionStatus.CERTIFIED):
        return jsonify({"error": "results are only available once voting has closed"}), 409
    return jsonify(logic.verify_and_tally(election))


@results_bp.route("/<int:election_id>/certify", methods=["POST"])
@require_role("super_admin")
def certify(election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        return jsonify({"error": "election not found"}), 404
    if election.status != ElectionStatus.CLOSED:
        return jsonify({"error": f"election is '{election.status.value}', can only certify from 'closed'"}), 409

    result = logic.verify_and_tally(election)
    if not result["chain_valid"]:
        return jsonify({"error": "cannot certify -- hash chain integrity check failed", **result}), 409

    election.status = ElectionStatus.CERTIFIED
    db.session.commit()
    return jsonify({"ok": True, "status": election.status.value, **result})
