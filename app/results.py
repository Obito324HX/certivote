"""
Post-election audit: walk the hash chain to prove it hasn't been tampered
with, then tally votes per position. Only available once voting is
CLOSED -- never while OPEN, which is the whole point of moving the "watch
it happen" moment to poll-close instead of live in-progress counts.
"""

from flask import Blueprint, jsonify

from .models import db, Election, ElectionStatus, Ballot
from .auth import require_role
from .security import hash_value

results_bp = Blueprint("results", __name__, url_prefix="/elections")


def _verify_and_tally(election: Election) -> dict:
    ballots = (Ballot.query
               .filter_by(election_id=election.id)
               .order_by(Ballot.id.asc())
               .all())

    expected_prev = hash_value(f"genesis:{election.id}")
    valid = True
    broken_at = None

    for b in ballots:
        if b.prev_hash != expected_prev:
            valid, broken_at = False, b.id
            break
        recomputed = Ballot.compute_hash(
            b.prev_hash, b.election_id, b.position_id, b.candidate_id, b.created_at.isoformat()
        )
        if recomputed != b.hash:
            valid, broken_at = False, b.id
            break
        expected_prev = b.hash

    root_hash = ballots[-1].hash if (valid and ballots) else None

    counts = {}
    for b in ballots:
        counts.setdefault(b.position_id, {})
        counts[b.position_id][b.candidate_id] = counts[b.position_id].get(b.candidate_id, 0) + 1

    tally = []
    for position in election.positions:
        results = []
        for c in position.candidates:
            results.append({
                "candidate_id": c.id,
                "name": c.name,
                "votes": counts.get(position.id, {}).get(c.id, 0),
            })
        results.sort(key=lambda x: -x["votes"])
        tally.append({"position_id": position.id, "title": position.title, "results": results})

    return {
        "chain_valid": valid,
        "broken_at_ballot_id": broken_at,
        "total_ballots": len(ballots),
        "root_hash": root_hash,
        "tally": tally,
    }


@results_bp.route("/<int:election_id>/audit", methods=["GET"])
@require_role("registrar", "super_admin", "observer")
def audit(election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        return jsonify({"error": "election not found"}), 404
    if election.status not in (ElectionStatus.CLOSED, ElectionStatus.CERTIFIED):
        return jsonify({"error": "results are only available once voting has closed"}), 409
    return jsonify(_verify_and_tally(election))


@results_bp.route("/<int:election_id>/certify", methods=["POST"])
@require_role("super_admin")
def certify(election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        return jsonify({"error": "election not found"}), 404
    if election.status != ElectionStatus.CLOSED:
        return jsonify({"error": f"election is '{election.status.value}', can only certify from 'closed'"}), 409

    result = _verify_and_tally(election)
    if not result["chain_valid"]:
        return jsonify({"error": "cannot certify -- hash chain integrity check failed", **result}), 409

    election.status = ElectionStatus.CERTIFIED
    db.session.commit()
    return jsonify({"ok": True, "status": election.status.value, **result})
