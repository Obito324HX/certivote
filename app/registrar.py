"""
JSON API for the registrar desk. All actual logic lives in
registrar_logic.py so the HTML admin pages (admin_ui.py) call the exact
same code.
"""

from flask import Blueprint, request, jsonify

from .auth import require_role, current_admin
from . import registrar_logic as logic

registrar_bp = Blueprint("registrar", __name__, url_prefix="/registrar")


@registrar_bp.route("/import-roster", methods=["POST"])
@require_role("super_admin")
def import_roster():
    if "file" not in request.files:
        return jsonify({"error": "no file uploaded, expected form field 'file'"}), 400
    result, status = logic.do_import_roster(request.files["file"])
    return jsonify(result), status


@registrar_bp.route("/lookup/<exam_number>", methods=["GET"])
@require_role("registrar", "super_admin")
def lookup(exam_number):
    result, status = logic.do_lookup(exam_number)
    return jsonify(result), status


@registrar_bp.route("/register", methods=["POST"])
@require_role("registrar", "super_admin")
def register():
    data = request.get_json(force=True)
    result, status = logic.do_register(
        current_admin().id, data.get("exam_number", "").strip(), data.get("phone_number", "").strip()
    )
    return jsonify(result), status


@registrar_bp.route("/rebind", methods=["POST"])
@require_role("registrar", "super_admin")
def rebind():
    data = request.get_json(force=True)
    result, status = logic.do_rebind(
        current_admin().id,
        data.get("exam_number", "").strip(),
        data.get("new_phone_number", "").strip(),
        data.get("approver_username", "").strip() or None,
        data.get("approver_password") or None,
    )
    return jsonify(result), status
