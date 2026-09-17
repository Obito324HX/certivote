"""
Data retention: purge voter PII a fixed number of days after the last
election of a cycle closes. Never purges while any election is still
DRAFT or OPEN, since that means a cycle is still in progress and voters
may still need their bound phone number.

What gets purged: full_name and phone_number (the two fields that let
someone quickly identify or contact a real person). exam_number and
section are kept -- they're needed to re-register the same student next
cycle, and are closer to an ID than contact information.

This is meant to run as a scheduled job (e.g. Render Cron Jobs), not
inside the web process. Exposed here as a Flask CLI command so it can be
triggered manually or wired into a scheduler.
"""

from datetime import datetime, timedelta

from .models import db, Voter, Election, ElectionStatus

DEFAULT_RETENTION_DAYS = 15


def purge_expired_voter_data(retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
    active_cycle = Election.query.filter(
        Election.status.in_([ElectionStatus.DRAFT, ElectionStatus.OPEN])
    ).first()
    if active_cycle:
        return 0

    latest_closed = (Election.query
                      .filter(Election.status.in_([ElectionStatus.CLOSED, ElectionStatus.CERTIFIED]))
                      .order_by(Election.voting_closes_at.desc())
                      .first())
    if latest_closed is None:
        return 0

    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    if latest_closed.voting_closes_at > cutoff:
        return 0

    voters = Voter.query.filter(Voter.phone_number.isnot(None)).all()
    for voter in voters:
        voter.full_name = "[purged]"
        voter.phone_number = None
        voter.phone_bound_at = None

    db.session.commit()
    return len(voters)
