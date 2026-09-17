"""
Election configuration routes.

Enforced here, not just described:
- Positions and candidates can only be added while an election is DRAFT.
- Opening an election (DRAFT -> OPEN) locks every position on it -- no
  candidate can be added or removed once voting is live. This is what
  makes "the ballot can't be changed mid-election" true in practice,
  not just a policy someone has to remember to follow.
"""

from datetime import datetime

from flask import Blueprint, request, jsonify

from .models import db, Election, ElectionScope, ElectionStatus, Position, Candidate
from .auth import require_role

elections_bp = Blueprint("elections", __name__, url_prefix="/elections")


def _parse_dt(value: str, field_name: str):
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError(f"'{field_name}' must be an ISO 8601 datetime, e.g. 2026-10-14T08:00:00")


@elections_bp.route("", methods=["POST"])
@require_role("super_admin")
def create_election():
    data = request.get_json(force=True)

    try:
        scope = ElectionScope(data.get("scope", ""))
    except ValueError:
        return jsonify({"error": "scope must be 'campus_wide' or 'sectional'"}), 400

    section = data.get("section")
    if scope == ElectionScope.SECTIONAL and not section:
        return jsonify({"error": "sectional elections require a 'section'"}), 400
    if scope == ElectionScope.CAMPUS_WIDE:
        section = None

    try:
        opens_at = _parse_dt(data.get("voting_opens_at"), "voting_opens_at")
        closes_at = _parse_dt(data.get("voting_closes_at"), "voting_closes_at")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if closes_at <= opens_at:
        return jsonify({"error": "voting_closes_at must be after voting_opens_at"}), 400

    election = Election(
        name=data.get("name", "").strip(),
        scope=scope,
        section=section,
        voting_opens_at=opens_at,
        voting_closes_at=closes_at,
        status=ElectionStatus.DRAFT,
    )
    db.session.add(election)
    db.session.commit()
    return jsonify(_election_summary(election)), 201


@elections_bp.route("", methods=["GET"])
@require_role("registrar", "super_admin", "observer")
def list_elections():
    elections = Election.query.order_by(Election.voting_opens_at).all()
    return jsonify([_election_summary(e) for e in elections])


@elections_bp.route("/<int:election_id>", methods=["GET"])
@require_role("registrar", "super_admin", "observer")
def get_election(election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        return jsonify({"error": "election not found"}), 404

    positions = []
    for p in election.positions:
        positions.append({
            "id": p.id,
            "title": p.title,
            "locked": p.locked,
            "candidates": [
                {"id": c.id, "name": c.name, "photo_url": c.photo_url, "manifesto": c.manifesto}
                for c in p.candidates
            ],
        })

    summary = _election_summary(election)
    summary["positions"] = positions
    return jsonify(summary)


@elections_bp.route("/<int:election_id>/positions", methods=["POST"])
@require_role("super_admin")
def add_position(election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        return jsonify({"error": "election not found"}), 404
    if election.status != ElectionStatus.DRAFT:
        return jsonify({"error": "positions can only be added while the election is in draft"}), 409

    data = request.get_json(force=True)
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    position = Position(election_id=election.id, title=title, locked=False)
    db.session.add(position)
    db.session.commit()
    return jsonify({"id": position.id, "title": position.title, "locked": position.locked}), 201


@elections_bp.route("/positions/<int:position_id>/candidates", methods=["POST"])
@require_role("super_admin")
def add_candidate(position_id):
    position = db.session.get(Position, position_id)
    if position is None:
        return jsonify({"error": "position not found"}), 404
    if position.locked:
        return jsonify({"error": "this position is locked -- election is no longer in draft"}), 409

    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    candidate = Candidate(
        position_id=position.id,
        name=name,
        photo_url=data.get("photo_url"),
        manifesto=data.get("manifesto"),
    )
    db.session.add(candidate)
    db.session.commit()
    return jsonify({
        "id": candidate.id, "name": candidate.name,
        "photo_url": candidate.photo_url, "manifesto": candidate.manifesto,
    }), 201


@elections_bp.route("/<int:election_id>/open", methods=["POST"])
@require_role("super_admin")
def open_election(election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        return jsonify({"error": "election not found"}), 404
    if election.status != ElectionStatus.DRAFT:
        return jsonify({"error": f"election is '{election.status.value}', can only open from 'draft'"}), 409
    if not election.positions:
        return jsonify({"error": "cannot open an election with no positions"}), 400
    for p in election.positions:
        if not p.candidates:
            return jsonify({"error": f"position '{p.title}' has no candidates"}), 400

    election.status = ElectionStatus.OPEN
    for p in election.positions:
        p.locked = True  # the actual lock-on-open enforcement
    db.session.commit()
    return jsonify(_election_summary(election))


@elections_bp.route("/<int:election_id>/close", methods=["POST"])
@require_role("super_admin")
def close_election(election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        return jsonify({"error": "election not found"}), 404
    if election.status != ElectionStatus.OPEN:
        return jsonify({"error": f"election is '{election.status.value}', can only close from 'open'"}), 409

    election.status = ElectionStatus.CLOSED
    db.session.commit()
    return jsonify(_election_summary(election))


def _election_summary(election: Election) -> dict:
    return {
        "id": election.id,
        "name": election.name,
        "scope": election.scope.value,
        "section": election.section,
        "status": election.status.value,
        "voting_opens_at": election.voting_opens_at.isoformat(),
        "voting_closes_at": election.voting_closes_at.isoformat(),
    }
