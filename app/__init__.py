import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask
from flask_migrate import Migrate

from .models import db


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

    from .auth import auth_bp
    from .registrar import registrar_bp
    from .elections import elections_bp
    from .voting import voting_bp
    from .results import results_bp
    from .voter_ui import voter_ui_bp
    from .admin_ui import admin_ui_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(registrar_bp)
    app.register_blueprint(elections_bp)
    app.register_blueprint(voting_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(voter_ui_bp)
    app.register_blueprint(admin_ui_bp)

    register_cli(app)
    return app


def register_cli(app):
    import click
    from .models import db, AdminUser, AdminRole

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.argument("password")
    @click.argument("role", type=click.Choice([r.value for r in AdminRole]))
    def create_admin(username, password, role):
        """Usage: flask create-admin <username> <password> <registrar|super_admin|observer>"""
        if AdminUser.query.filter_by(username=username).first():
            click.echo(f"'{username}' already exists.")
            return
        user = AdminUser(username=username, role=AdminRole(role))
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created {role} account '{username}'.")
