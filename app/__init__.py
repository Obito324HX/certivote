import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, redirect, url_for
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

from .models import db

csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]

    app.config["SMS_MODE"] = os.environ.get("SMS_MODE", "sandbox")
    app.config["AT_USERNAME"] = os.environ.get("AT_USERNAME", "sandbox")
    app.config["AT_API_KEY"] = os.environ.get("AT_API_KEY", "")

    if os.environ.get("ENV") == "production":
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["SESSION_COOKIE_HTTPONLY"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    db.init_app(app)
    Migrate(app, db)
    csrf.init_app(app)

    from .auth import auth_bp
    from .registrar import registrar_bp
    from .elections import elections_bp
    from .voting import voting_bp
    from .results import results_bp
    from .voter_ui import voter_ui_bp
    from .admin_ui import admin_ui_bp
    from .public_ui import public_ui_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(registrar_bp)
    app.register_blueprint(elections_bp)
    app.register_blueprint(voting_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(voter_ui_bp)
    app.register_blueprint(admin_ui_bp)
    app.register_blueprint(public_ui_bp)

    csrf.exempt(auth_bp)
    csrf.exempt(registrar_bp)
    csrf.exempt(elections_bp)
    csrf.exempt(voting_bp)
    csrf.exempt(results_bp)

    @app.route("/")
    def root():
        return redirect(url_for("voter_ui.index"))

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self'; "
            "script-src 'none'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "img-src 'self' data:;"
        )
        if os.environ.get("ENV") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    register_cli(app)
    return app


def register_cli(app):
    import click
    from .models import db, AdminUser, AdminRole
    from .retention import purge_expired_voter_data, DEFAULT_RETENTION_DAYS

    MIN_PASSWORD_LENGTH = 10

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.argument("password")
    @click.argument("role", type=click.Choice([r.value for r in AdminRole]))
    def create_admin(username, password, role):
        """Usage: flask create-admin <username> <password> <registrar|super_admin|observer>"""
        if len(password) < MIN_PASSWORD_LENGTH:
            click.echo(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
            return
        if AdminUser.query.filter_by(username=username).first():
            click.echo(f"'{username}' already exists.")
            return
        user = AdminUser(username=username, role=AdminRole(role))
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created {role} account '{username}'.")

    @app.cli.command("purge-expired-voters")
    @click.option("--days", default=DEFAULT_RETENTION_DAYS, help="Retention period in days.")
    def purge_expired_voters(days):
        """
        Purges voter PII (name, phone) once the last election of a cycle
        has been closed for at least --days days. Safe to run repeatedly
        (e.g. daily via a scheduler) -- it's a no-op while a cycle is
        still active or not yet old enough.
        """
        count = purge_expired_voter_data(retention_days=days)
        if count:
            click.echo(f"Purged PII for {count} voter(s).")
        else:
            click.echo("Nothing to purge (cycle still active, or not old enough yet).")
