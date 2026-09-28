"""
Super-admin HTML pages for election setup: picking a draft election,
viewing its positions, and adding candidates with a photo -- uploaded
straight into the database (see models.Candidate.photo_data) rather
than to local disk, since Render's free-tier filesystem doesn't survive
a redeploy or spin-down but Postgres does.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash

from .models import db, Election, ElectionStatus, Position, Candidate
from .auth import require_role_page

election_ui_bp = Blueprint("election_ui", __name__, url_prefix="/admin/elections")

ALLOWED_PHOTO_TYPES = {
    "image/jpeg": "jpeg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_PHOTO_BYTES = 500 * 1024  # 500KB -- keeps ballot/results pages light on a slow connection


@election_ui_bp.route("/")
@require_role_page("super_admin")
def index():
    drafts = (Election.query
              .filter_by(status=ElectionStatus.DRAFT)
              .order_by(Election.voting_opens_at)
              .all())
    return render_template("election_setup_index.html", elections=drafts)


@election_ui_bp.route("/<int:election_id>")
@require_role_page("super_admin")
def show(election_id):
    election = db.session.get(Election, election_id)
    if election is None:
        flash("Election not found.")
        return redirect(url_for("election_ui.index"))
    return render_template("election_setup_detail.html", election=election)


@election_ui_bp.route("/positions/<int:position_id>/candidates", methods=["POST"])
@require_role_page("super_admin")
def add_candidate(position_id):
    position = db.session.get(Position, position_id)
    if position is None:
        flash("Position not found.")
        return redirect(url_for("election_ui.index"))
    if position.locked:
        flash("This position is locked -- the election is no longer in draft.")
        return redirect(url_for("election_ui.show", election_id=position.election_id))

    name = request.form.get("name", "").strip()
    manifesto = request.form.get("manifesto", "").strip() or None
    if not name:
        flash("Candidate name is required.")
        return redirect(url_for("election_ui.show", election_id=position.election_id))

    photo_data, photo_mimetype = None, None
    file = request.files.get("photo")
    if file and file.filename:
        if file.mimetype not in ALLOWED_PHOTO_TYPES:
            flash("Photo must be a JPEG, PNG, or WebP image.")
            return redirect(url_for("election_ui.show", election_id=position.election_id))

        raw = file.read()
        if len(raw) > MAX_PHOTO_BYTES:
            flash("Photo must be under 500KB -- please resize it and try again.")
            return redirect(url_for("election_ui.show", election_id=position.election_id))

        photo_data, photo_mimetype = raw, file.mimetype

    db.session.add(Candidate(
        position_id=position.id, name=name, manifesto=manifesto,
        photo_data=photo_data, photo_mimetype=photo_mimetype,
    ))
    db.session.commit()
    flash(f"Added {name} to {position.title}.")
    return redirect(url_for("election_ui.show", election_id=position.election_id))
