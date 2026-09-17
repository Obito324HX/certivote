"""
Public election pages -- no login required. This is the "watch it
happen" transparency feature, deliberately split into two safe moments:
- While OPEN: turnout count only, never a candidate breakdown, since a
  live in-progress tally can influence undecided voters and (in small
  electorates) risks correlating a visible moment with a specific
  student's ballot.
- Once CERTIFIED: the full reveal, built directly on the same hash-chain
  verification used for certification -- so the "election night" moment
  IS the audit proof, not a separate display of numbers.
CLOSED-but-not-yet-CERTIFIED shows neither: results are pending official
verification, not partially visible.
"""

from flask import Blueprint, render_template, abort

from .models import db, Election, ElectionStatus
from . import results_logic as logic

public_ui_bp = Blueprint("public_ui", __name__, url_prefix="/results")


@public_ui_bp.route("/")
def index():
    elections = (Election.query
                 .filter(Election.status != ElectionStatus.DRAFT)
                 .order_by(Election.voting_opens_at.desc())
                 .all())
    return render_template("public_index.html", elections=elections)


@public_ui_bp.route("/<int:election_id>")
def show(election_id):
    election = db.session.get(Election, election_id)
    if election is None or election.status == ElectionStatus.DRAFT:
        abort(404)

    if election.status == ElectionStatus.OPEN:
        return render_template(
            "public_open.html", election=election,
            votes_cast=logic.votes_cast_count(election),
            eligible=logic.eligible_voter_count(election),
        )

    if election.status == ElectionStatus.CLOSED:
        return render_template("public_closed.html", election=election)

    result = logic.verify_and_tally(election)
    return render_template("public_results.html", election=election, result=result)
