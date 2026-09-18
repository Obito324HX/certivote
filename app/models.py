"""
Certivote data models.

Core design principle (do not violate this while extending the schema):
Voter identity and ballot content are stored in separate tables with NO
foreign key link between them. VoteStatus records THAT someone voted.
Ballot records WHAT was voted, anonymously. Never add a voter_id column
to Ballot, and never join the two tables in application code.
"""

import hashlib
import enum
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class ElectionScope(enum.Enum):
    CAMPUS_WIDE = "campus_wide"
    SECTIONAL = "sectional"


class ElectionStatus(enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"
    CERTIFIED = "certified"


class AdminRole(enum.Enum):
    REGISTRAR = "registrar"
    SUPER_ADMIN = "super_admin"
    OBSERVER = "observer"


class Voter(db.Model):
    """
    pending_phone_number / pending_rebind_effective_at implement the
    re-bind time-lock: while an election is open, a re-bind doesn't take
    effect immediately -- it's staged here and only promoted to
    phone_number once effective_at has passed (see
    registrar_logic.apply_pending_rebind).
    """
    __tablename__ = "voters"

    id = db.Column(db.Integer, primary_key=True)
    exam_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    section = db.Column(db.String(64), nullable=False)
    full_name = db.Column(db.String(128), nullable=False)

    phone_number = db.Column(db.String(20), nullable=True)
    phone_bound_at = db.Column(db.DateTime, nullable=True)

    pending_phone_number = db.Column(db.String(20), nullable=True)
    pending_rebind_effective_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Election(db.Model):
    __tablename__ = "elections"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    scope = db.Column(db.Enum(ElectionScope), nullable=False)
    section = db.Column(db.String(64), nullable=True)

    voting_opens_at = db.Column(db.DateTime, nullable=False)
    voting_closes_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.Enum(ElectionStatus), default=ElectionStatus.DRAFT, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    positions = db.relationship("Position", backref="election", lazy=True)


class Position(db.Model):
    __tablename__ = "positions"

    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey("elections.id"), nullable=False)
    title = db.Column(db.String(64), nullable=False)
    locked = db.Column(db.Boolean, default=False)

    candidates = db.relationship("Candidate", backref="position", lazy=True)


class Candidate(db.Model):
    __tablename__ = "candidates"

    id = db.Column(db.Integer, primary_key=True)
    position_id = db.Column(db.Integer, db.ForeignKey("positions.id"), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    photo_url = db.Column(db.String(256), nullable=True)
    manifesto = db.Column(db.Text, nullable=True)


class VoteStatus(db.Model):
    """
    The UniqueConstraint below is a real database-level guarantee against
    double voting -- it makes concurrent conflicting inserts fail
    atomically at the database engine itself; the application code just
    catches the resulting IntegrityError (see
    voting_logic._validate_and_write_vote). Equivalent to row-locking for
    an insert-once pattern, not a weaker substitute for it.
    """
    __tablename__ = "vote_status"

    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey("elections.id"), nullable=False)
    voter_id = db.Column(db.Integer, db.ForeignKey("voters.id"), nullable=False)
    voted_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("election_id", "voter_id", name="uq_one_vote_per_election"),
    )


class Ballot(db.Model):
    __tablename__ = "ballots"

    id = db.Column(db.Integer, primary_key=True)
    election_id = db.Column(db.Integer, db.ForeignKey("elections.id"), nullable=False)
    position_id = db.Column(db.Integer, db.ForeignKey("positions.id"), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id"), nullable=False)

    prev_hash = db.Column(db.String(64), nullable=False)
    hash = db.Column(db.String(64), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @staticmethod
    def compute_hash(prev_hash: str, election_id: int, position_id: int,
                      candidate_id: int, timestamp: str) -> str:
        payload = f"{prev_hash}|{election_id}|{position_id}|{candidate_id}|{timestamp}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class OtpToken(db.Model):
    """
    requesting_ip is logged for the audit trail (never tied to the
    ballot -- this is about detecting abuse patterns on the OTP
    endpoint itself, not about deanonymizing a vote).
    """
    __tablename__ = "otp_tokens"

    id = db.Column(db.Integer, primary_key=True)
    voter_id = db.Column(db.Integer, db.ForeignKey("voters.id"), nullable=False)
    election_id = db.Column(db.Integer, db.ForeignKey("elections.id"), nullable=False)
    code_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    attempts = db.Column(db.Integer, default=0)
    requesting_ip = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class VotingSession(db.Model):
    __tablename__ = "voting_sessions"

    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    voter_id = db.Column(db.Integer, db.ForeignKey("voters.id"), nullable=False)
    election_id = db.Column(db.Integer, db.ForeignKey("elections.id"), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AdminUser(db.Model):
    """
    failed_login_attempts / locked_until implement account lockout:
    5 wrong passwords locks the account for 15 minutes. Reset on any
    successful login.
    """
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.Enum(AdminRole), nullable=False)

    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)


class RegistrarAuditLog(db.Model):
    __tablename__ = "registrar_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"), nullable=False)
    voter_id = db.Column(db.Integer, db.ForeignKey("voters.id"), nullable=False)
    action = db.Column(db.String(32), nullable=False)  # "register" | "rebind" | "rebind_pending" | "kiosk_vote"

    old_phone_hash = db.Column(db.String(64), nullable=True)
    new_phone_hash = db.Column(db.String(64), nullable=True)

    approved_by_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
