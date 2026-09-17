"""
Core voting logic, extracted from voting.py so both the JSON API
(voting.py) and the server-rendered voter pages (voter_ui.py) call the
exact same code -- no duplicated business rules between the two.
"""

import secrets
from datetime import datetime, timedelta

from .models import (
    db, Voter, Election, ElectionStatus, ElectionScope,
    OtpToken, VotingSession, VoteStatus, Ballot,
)
from .security import hash_value
from .sms import send_sms
from sqlalchemy.exc import IntegrityError

OTP_TTL_MINUTES = 5
OTP_COOLDOWN_SECONDS = 30
OTP_MAX_ATTEMPTS = 5
SESSION_TTL_MINUTES = 10


def eligible_election_or_error(voter: Voter, election: Election):
    if election.status != ElectionStatus.OPEN:
        return "this election is not currently open for voting"
    if election.scope == ElectionScope.SECTIONAL and election.section != voter.section:
        return "you are not eligible to vote in this election"
    if VoteStatus.query.filter_by(election_id=election.id, voter_id=voter.id).first():
        return "you have already voted in this election"
    return None


def eligible_open_elections(voter: Voter):
    open_elections = Election.query.filter_by(status=ElectionStatus.OPEN).all()
    return [e for e in open_elections if eligible_election_or_error(voter, e) is None]


def do_request_otp(exam_number: str, election_id: int):
    voter = Voter.query.filter_by(exam_number=exam_number).first()
    if voter is None:
        return {"error": "exam number not found"}, 404
    if voter.phone_number is None:
        return {"error": "no phone number on file -- visit the registration desk first"}, 400

    election = db.session.get(Election, election_id)
    if election is None:
        return {"error": "election not found"}, 404

    reason = eligible_election_or_error(voter, election)
    if reason:
        return {"error": reason}, 403

    latest = (OtpToken.query
              .filter_by(voter_id=voter.id, election_id=election.id)
              .order_by(OtpToken.created_at.desc())
              .first())
    if latest and not latest.used:
        seconds_since = (datetime.utcnow() - latest.created_at).total_seconds()
        if seconds_since < OTP_COOLDOWN_SECONDS:
            wait = int(OTP_COOLDOWN_SECONDS - seconds_since)
            return {"error": f"please wait {wait}s before requesting another OTP"}, 429
        latest.used = True

    otp = f"{secrets.randbelow(1_000_000):06d}"
    token = OtpToken(
        voter_id=voter.id,
        election_id=election.id,
        code_hash=hash_value(otp),
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES),
    )
    db.session.add(token)
    db.session.commit()

    send_sms(voter.phone_number, f"Your Certivote code is {otp}. It expires in {OTP_TTL_MINUTES} minutes.")
    return {"ok": True, "message": "OTP sent"}, 200


def do_verify_otp(exam_number: str, election_id: int, otp: str):
    voter = Voter.query.filter_by(exam_number=exam_number).first()
    if voter is None:
        return {"error": "exam number not found"}, 404

    token = (OtpToken.query
             .filter_by(voter_id=voter.id, election_id=election_id, used=False)
             .order_by(OtpToken.created_at.desc())
             .first())
    if token is None:
        return {"error": "no valid OTP request found -- request one first"}, 400
    if datetime.utcnow() > token.expires_at:
        return {"error": "OTP expired -- request a new one"}, 400
    if token.attempts >= OTP_MAX_ATTEMPTS:
        token.used = True
        db.session.commit()
        return {"error": "too many incorrect attempts -- request a new OTP"}, 429

    if hash_value(otp) != token.code_hash:
        token.attempts += 1
        db.session.commit()
        return {"error": "incorrect OTP"}, 401

    token.used = True
    raw_session_token = secrets.token_urlsafe(32)
    session_row = VotingSession(
        token_hash=hash_value(raw_session_token),
        voter_id=voter.id,
        election_id=election_id,
        expires_at=datetime.utcnow() + timedelta(minutes=SESSION_TTL_MINUTES),
    )
    db.session.add(session_row)
    db.session.commit()

    return {"voting_session_token": raw_session_token, "expires_in_minutes": SESSION_TTL_MINUTES}, 200


def do_cast_ballot(raw_token: str, selections: list):
    session_row = VotingSession.query.filter_by(token_hash=hash_value(raw_token)).first()
    if session_row is None:
        return {"error": "invalid voting session"}, 401
    if session_row.used:
        return {"error": "this voting session has already been used"}, 409
    if datetime.utcnow() > session_row.expires_at:
        return {"error": "voting session expired -- verify your OTP again"}, 401

    election = db.session.get(Election, session_row.election_id)
    if election is None or election.status != ElectionStatus.OPEN:
        return {"error": "this election is no longer open"}, 409

    positions = {p.id: p for p in election.positions}
    submitted_position_ids = {s.get("position_id") for s in selections}
    if submitted_position_ids != set(positions.keys()):
        return {"error": "your ballot must include exactly one selection for every position"}, 400

    for s in selections:
        position = positions[s["position_id"]]
        candidate_ids = {c.id for c in position.candidates}
        if s.get("candidate_id") not in candidate_ids:
            return {"error": f"invalid candidate for position '{position.title}'"}, 400

    voter = db.session.get(Voter, session_row.voter_id)

    try:
        db.session.add(VoteStatus(election_id=election.id, voter_id=voter.id))
        db.session.flush()

        last_ballot = (Ballot.query
                       .filter_by(election_id=election.id)
                       .order_by(Ballot.id.desc())
                       .first())
        prev_hash = last_ballot.hash if last_ballot else hash_value(f"genesis:{election.id}")

        for s in sorted(selections, key=lambda x: x["position_id"]):
            timestamp = datetime.utcnow().isoformat()
            new_hash = Ballot.compute_hash(prev_hash, election.id, s["position_id"], s["candidate_id"], timestamp)
            db.session.add(Ballot(
                election_id=election.id,
                position_id=s["position_id"],
                candidate_id=s["candidate_id"],
                prev_hash=prev_hash,
                hash=new_hash,
                created_at=datetime.fromisoformat(timestamp),
            ))
            prev_hash = new_hash

        session_row.used = True
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"error": "you have already voted in this election"}, 409

    send_sms(
        voter.phone_number,
        f"Your vote was recorded at {datetime.utcnow().strftime('%H:%M')}. "
        f"If this wasn't you, contact the registration desk immediately.",
    )
    return {"ok": True, "message": "vote recorded"}, 200
