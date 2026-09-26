"""
Shared election-results logic: hash chain verification + tally, and
turnout counting. Used by both the authenticated audit route
(results.py) and the public no-login pages (public_ui.py).
"""

from .models import db, Election, ElectionScope, Ballot, Voter, VoteStatus
from .security import hash_value


def verify_and_tally(election: Election) -> dict:
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
                "photo_url": c.photo_url,
                "votes": counts.get(position.id, {}).get(c.id, 0),
            })
        results.sort(key=lambda x: -x["votes"])
        for i, r in enumerate(results):
            r["is_winner"] = i < position.seats and r["votes"] > 0
        tally.append({
            "position_id": position.id,
            "title": position.title,
            "seats": position.seats,
            "results": results,
        })

    return {
        "chain_valid": valid,
        "broken_at_ballot_id": broken_at,
        "total_ballots": len(ballots),
        "root_hash": root_hash,
        "tally": tally,
    }


def eligible_voter_count(election: Election) -> int:
    query = Voter.query.filter(Voter.phone_number.isnot(None))
    if election.scope == ElectionScope.SECTIONAL:
        query = query.filter_by(section=election.section)
    return query.count()


def votes_cast_count(election: Election) -> int:
    return VoteStatus.query.filter_by(election_id=election.id).count()
