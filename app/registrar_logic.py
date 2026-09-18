"""
Registrar-desk logic, extracted so both the JSON API (registrar.py) and
the HTML admin pages (admin_ui.py) call the exact same code.
"""

import csv
import io
from datetime import datetime, timedelta

from .models import db, Voter, AdminUser, RegistrarAuditLog, Election, ElectionStatus
from .security import hash_phone, mask_phone
from .sms import send_sms

REBIND_DELAY_MINUTES = 30


def any_election_open() -> bool:
    return db.session.query(
        Election.query.filter_by(status=ElectionStatus.OPEN).exists()
    ).scalar()


def apply_pending_rebind(voter: Voter) -> None:
    if (voter.pending_phone_number
            and voter.pending_rebind_effective_at
            and datetime.utcnow() >= voter.pending_rebind_effective_at):
        voter.phone_number = voter.pending_phone_number
        voter.phone_bound_at = datetime.utcnow()
        voter.pending_phone_number = None
        voter.pending_rebind_effective_at = None
        db.session.commit()


def do_import_roster(file_storage):
    raw = file_storage.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(raw))

    required_cols = {"exam_number", "section", "full_name"}
    if not required_cols.issubset(set(reader.fieldnames or [])):
        return {"error": f"CSV must have columns: {sorted(required_cols)}"}, 400

    created, updated = 0, 0
    for row in reader:
        exam_number = row["exam_number"].strip()
        voter = Voter.query.filter_by(exam_number=exam_number).first()
        if voter is None:
            voter = Voter(
                exam_number=exam_number,
                section=row["section"].strip(),
                full_name=row["full_name"].strip(),
            )
            db.session.add(voter)
            created += 1
        else:
            voter.section = row["section"].strip()
            voter.full_name = row["full_name"].strip()
            updated += 1

    db.session.commit()
    return {"created": created, "updated": updated}, 200


def do_lookup(exam_number: str):
    voter = Voter.query.filter_by(exam_number=exam_number).first()
    if voter is None:
        return {"error": "no voter with that exam number in the roster"}, 404

    apply_pending_rebind(voter)

    return {
        "exam_number": voter.exam_number,
        "full_name": voter.full_name,
        "section": voter.section,
        "phone_bound": voter.phone_number is not None,
        "phone_masked": mask_phone(voter.phone_number),
        "pending_rebind": voter.pending_phone_number is not None,
        "pending_effective_at": (voter.pending_rebind_effective_at.isoformat()
                                  if voter.pending_rebind_effective_at else None),
    }, 200


def do_register(actor_id: int, exam_number: str, phone_number: str):
    voter = Voter.query.filter_by(exam_number=exam_number).first()
    if voter is None:
        return {"error": "no voter with that exam number in the roster"}, 404
    if voter.phone_number is not None:
        return {"error": "voter already has a bound phone number; use rebind instead"}, 409

    voter.phone_number = phone_number
    voter.phone_bound_at = datetime.utcnow()

    db.session.add(RegistrarAuditLog(
        actor_id=actor_id,
        voter_id=voter.id,
        action="register",
        old_phone_hash=None,
        new_phone_hash=hash_phone(phone_number),
    ))
    db.session.commit()
    return {"ok": True, "exam_number": exam_number, "phone_masked": mask_phone(phone_number)}, 200


def do_rebind(actor_id: int, exam_number: str, new_phone_number: str,
              approver_username: str = None, approver_password: str = None):
    voter = Voter.query.filter_by(exam_number=exam_number).first()
    if voter is None:
        return {"error": "no voter with that exam number in the roster"}, 404

    apply_pending_rebind(voter)

    approver = None
    election_open = any_election_open()
    if election_open:
        if not approver_username or not approver_password:
            return {
                "error": "an election is currently open -- rebind requires a second "
                         "admin's approver username and password"
            }, 400

        approver = AdminUser.query.filter_by(username=approver_username).first()
        if approver is None or not approver.check_password(approver_password):
            return {"error": "approver credentials invalid"}, 401
        if approver.id == actor_id:
            return {"error": "approver must be a different admin than the one performing the rebind"}, 400
        if approver.role.value not in ("registrar", "super_admin"):
            return {"error": "approver must be a registrar or super_admin"}, 403

    old_hash = hash_phone(voter.phone_number) if voter.phone_number else None
    new_hash = hash_phone(new_phone_number)

    if election_open:
        old_phone_for_notice = voter.phone_number
        voter.pending_phone_number = new_phone_number
        voter.pending_rebind_effective_at = datetime.utcnow() + timedelta(minutes=REBIND_DELAY_MINUTES)

        db.session.add(RegistrarAuditLog(
            actor_id=actor_id, voter_id=voter.id, action="rebind_pending",
            old_phone_hash=old_hash, new_phone_hash=new_hash,
            approved_by_id=approver.id if approver else None,
        ))
        db.session.commit()

        if old_phone_for_notice:
            send_sms(
                old_phone_for_notice,
                f"Your Certivote voting phone number is being changed. If you did not "
                f"request this, contact the registration desk immediately. The change "
                f"takes effect in {REBIND_DELAY_MINUTES} minutes.",
            )
        return {
            "ok": True, "exam_number": exam_number,
            "message": f"Re-bind scheduled -- takes effect in {REBIND_DELAY_MINUTES} minutes.",
        }, 200

    voter.phone_number = new_phone_number
    voter.phone_bound_at = datetime.utcnow()

    db.session.add(RegistrarAuditLog(
        actor_id=actor_id, voter_id=voter.id, action="rebind",
        old_phone_hash=old_hash, new_phone_hash=new_hash, approved_by_id=None,
    ))
    db.session.commit()
    return {"ok": True, "exam_number": exam_number, "phone_masked": mask_phone(new_phone_number)}, 200
