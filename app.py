import base64
from datetime import datetime, timedelta
from email.header import Header
from functools import lru_cache
import os
import random
import secrets
import string
from smtplib import SMTPSenderRefused
import traceback
from typing import List, Optional, cast
from flask import (
    Flask,
    make_response,
    redirect,
    request,
    jsonify,
    render_template,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from flasgger import Swagger
from flask_cors import CORS
from requests import HTTPError
import serpapi
import yaml
from sqlalchemy.orm import Mapper
from sqlalchemy import inspect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.message import EmailMessage
from email.policy import SMTP
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
)

# Für den neuen 2.0-Stil
from sqlalchemy.orm import Mapped, mapped_column, relationship

app = Flask(__name__)


# Intelligente Database URI Konfiguration
def get_database_uri():
    """Erstellt eine korrekte SQLAlchemy Database URI und stellt sicher, dass das Verzeichnis existiert"""
    database_uri = os.getenv("DATABASE_URI") or "sqlite:///storage.db"

    # Wenn es sich um einen einfachen Dateipfad handelt, füge sqlite:/// hinzu
    if not database_uri.startswith(
        ("sqlite://", "postgresql://", "mysql://", "mysql+pymysql://")
    ):
        # Behandle sowohl absolute als auch relative Pfade
        if os.path.isabs(database_uri):
            database_uri = f"sqlite:///{database_uri}"
        else:
            database_uri = f"sqlite:///{database_uri}"

    # Extrahiere den Dateipfad aus der URI für die Verzeichniserstellung (nur für SQLite)
    if database_uri.startswith("sqlite:///"):
        file_path = database_uri[10:]  # Entferne "sqlite:///"

        # Konvertiere relative Pfade zu absoluten Pfaden
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)
            database_uri = f"sqlite:///{file_path}"

        # Stelle sicher, dass das Verzeichnis existiert
        directory = os.path.dirname(file_path)
        if directory and directory != "." and not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
                print(f"Created database directory: {directory}")
            except Exception as e:
                print(f"Warning: Could not create database directory {directory}: {e}")
                print(f"Current working directory: {os.getcwd()}")
                print(f"Directory permissions needed for: {directory}")

        # Prüfe ob das Verzeichnis beschreibbar ist
        if directory and directory != "." and os.path.exists(directory):
            if not os.access(directory, os.W_OK):
                print(
                    f"Warning: No write permission for database directory: {directory}"
                )

    print(f"Using database URI: {database_uri}")
    return database_uri


app.config["SQLALCHEMY_DATABASE_URI"] = get_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "TeStK3y123!")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False  # 15 Minuten
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = 604800  # 7 Tage
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER")
app.config["MAIL_PORT"] = os.getenv("MAIL_PORT", 465)
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER")

# image size limit 5MB, allowed extensions and allowed content types for images
app.config["ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif"}
app.config["ALLOWED_CONTENT_TYPES"] = {
    "data:image/png",
    "data:image/jpeg",
    "data:image/jpg",
    "data:image/gif",
}

# CORS konfigurieren
CORS(app)
CORS(app, origins=[os.getenv("FRONTEND_URL") or "http://localhost:3000"])

app_url = os.getenv("APP_URL") or "http://localhost:4000"

# Swagger initialisieren
with open("swagger.yaml", "r") as f:
    swagger_template = yaml.safe_load(f)
    swagger_template["host"] = app_url.split("://")[1]
    swagger_template["schemes"] = [app_url.split("://")[0]]

swagger = Swagger(app, template=swagger_template)
jwt = JWTManager(app)
mail = Mail(app)
db = SQLAlchemy(app)


### GLOBALE FEHLERBEHANDLER ###
@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": "Bad Request"}), 400


@app.errorhandler(401)
def unauthorized(error):
    return jsonify({"error": "Unauthorized"}), 401


@app.errorhandler(403)
def forbidden(error):
    return jsonify({"error": "Forbidden"}), 403


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not Found"}), 404


@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": "Method Not Allowed"}), 405


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({"error": "Internal Server Error"}), 500


@app.errorhandler(Exception)
def handle_exception(e):
    """Global exception handler für bessere Fehlerbehandlung in Produktion"""
    # Log the error
    app.logger.error(f"Unhandled exception: {str(e)}", exc_info=True)

    # Rollback any pending database transactions
    try:
        db.session.rollback()
    except:
        pass

    # Return JSON error response
    return (
        jsonify({"error": "Internal Server Error", "message": "Something went wrong"}),
        500,
    )


# Request Timeout Handler
@app.before_request
def before_request():
    """Request preprocessing - kann für Timeouts und Limits verwendet werden"""
    # Set maximum request size (10MB)
    if request.content_length and request.content_length > 10 * 1024 * 1024:
        return jsonify({"error": "Request too large"}), 413


### MODELLDEFINITIONEN im SQLAlchemy 2.0-Stil ###
class User(db.Model):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    username: Mapped[str] = mapped_column(db.String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(db.String(128), nullable=False)
    email: Mapped[str] = mapped_column(db.String(120), unique=False)
    image: Mapped[Optional[str]] = mapped_column(db.Text)
    admin: Mapped[bool] = mapped_column(db.Boolean, default=False)
    persons: Mapped[int] = mapped_column(db.Integer, default=1)
    activated: Mapped[bool] = mapped_column(db.Boolean, default=False)
    # Beziehungen zu den benutzerspezifischen Daten:
    storage_items: Mapped[List["StorageItem"]] = relationship(
        "StorageItem", backref="user"
    )
    basket_items: Mapped[List["BasketItem"]] = relationship(
        "BasketItem", backref="user"
    )
    groups: Mapped[List["UserGroup"]] = relationship("UserGroup", backref="user")

    def __init__(self, username: str):
        self.username = username

    def set_role(self, role: str):
        self.admin = role == "admin"

    def set_email(self, email: str):
        self.email = email.lower()

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __to_dict__(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "image": self.image,
            "admin": self.admin,
            "persons": self.persons,
            "activated": self.activated,
            "groups": [group.id for group in self.groups],
        }


class UserGroup(db.Model):
    __tablename__ = "user_group"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    group_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("group.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(db.String(50), default="member")  # admin, member
    joined_at: Mapped[Optional[datetime]] = mapped_column(
        db.DateTime, default=db.func.now()
    )

    # Beziehungen
    group: Mapped["Group"] = relationship("Group", back_populates="members")

    def __init__(self, user_id: int, group_id: int, role: str = "member"):
        self.user_id = user_id
        self.group_id = group_id
        self.role = role


class Group(db.Model):
    __tablename__ = "group"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(db.String(500))
    image: Mapped[Optional[str]] = mapped_column(db.Text)  # Base64-kodiertes Bild
    created_by: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        db.DateTime, default=db.func.now()
    )
    invite_code: Mapped[str] = mapped_column(db.String(10), unique=True, nullable=False)

    # Beziehungen
    members: Mapped[List["UserGroup"]] = relationship(
        "UserGroup", back_populates="group"
    )
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])

    def __init__(
        self, name: str, description: str, created_by: int, image: Optional[str] = None
    ):
        self.name = name
        self.description = description
        self.image = image
        self.created_by = created_by
        self.invite_code = self.generate_invite_code()

    def generate_invite_code(self):
        import random
        import string

        return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


class GroupInvitation(db.Model):
    __tablename__ = "group_invitation"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("group.id"), nullable=False
    )
    invited_by: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    invited_email: Mapped[str] = mapped_column(db.String(120), nullable=False)
    invite_token: Mapped[str] = mapped_column(
        db.String(100), unique=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        db.String(20), default="pending"
    )  # pending, accepted, declined
    created_at: Mapped[Optional[datetime]] = mapped_column(
        db.DateTime, default=db.func.now()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(db.DateTime)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(db.DateTime)

    # Beziehungen
    group: Mapped["Group"] = relationship("Group")
    inviter: Mapped["User"] = relationship("User")
    invite_url: Mapped[Optional[str]] = mapped_column(db.String(500))

    def __init__(
        self,
        group_id: int,
        invited_by: int,
        invited_email: str,
        invite_token: str = "",
        invite_url: str = "",
    ):
        self.group_id = group_id
        self.invited_by = invited_by
        self.invited_email = invited_email
        self.invite_token = invite_token or self.generate_invite_token()
        self.invite_url = invite_url
        from datetime import datetime, timedelta

        self.expires_at = datetime.utcnow() + timedelta(hours=48)

    def generate_invite_token(self):
        import secrets

        return secrets.token_urlsafe(32)


class StorageItem(db.Model):
    __tablename__ = "storage_item"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(100), nullable=False)
    amount: Mapped[int] = mapped_column(db.Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    categories: Mapped[Optional[str]] = mapped_column(db.String(500))
    lowestAmount: Mapped[int] = mapped_column(db.Integer, nullable=False)
    midAmount: Mapped[int] = mapped_column(db.Integer, nullable=False)
    unit: Mapped[str] = mapped_column(db.String(50), nullable=False)
    packageQuantity: Mapped[Optional[int]] = mapped_column(db.Integer)
    packageUnit: Mapped[Optional[str]] = mapped_column(db.String(50))
    storageLocation: Mapped[str] = mapped_column(db.String(100), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(db.String(200))
    nutrient: Mapped[Optional["Nutrient"]] = relationship(
        "Nutrient",
        uselist=False,
        back_populates="storage_item",
        cascade="all, delete-orphan",
    )
    __table_args__ = (
        db.UniqueConstraint(
            "name",
            "unit",
            "user_id",
            name="unique_name_location_unit_user",
        ),
    )

    def __init__(
        self,
        name: str,
        amount: int,
        categories: str,
        lowestAmount: int,
        midAmount: int,
        unit: str,
        user_id: int,
        packageQuantity: Optional[int] = None,
        packageUnit: Optional[str] = None,
        storageLocation: str = "",
        icon: str = "",
    ):
        self.name = name
        self.amount = amount
        self.categories = categories
        self.lowestAmount = lowestAmount
        self.midAmount = midAmount
        self.unit = unit
        self.packageQuantity = packageQuantity
        self.packageUnit = packageUnit
        self.storageLocation = storageLocation
        self.icon = icon
        self.user_id = user_id


class BasketItem(db.Model):
    __tablename__ = "basket_item"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(db.String(100), nullable=False)
    amount: Mapped[int] = mapped_column(db.Integer, nullable=True)
    categories: Mapped[Optional[str]] = mapped_column(db.String(500))
    icon: Mapped[Optional[str]] = mapped_column(db.String(200))

    def __init__(
        self, name: str, amount: int, categories: str, icon: str, user_id: int
    ):
        self.name = name
        self.amount = amount
        self.icon = icon
        self.categories = categories
        self.user_id = user_id


class Nutrient(db.Model):
    __tablename__ = "nutrient"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    description: Mapped[str] = mapped_column(db.String(200), nullable=False)
    user_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    unit: Mapped[str] = mapped_column(db.String(50), nullable=False)
    amount: Mapped[float] = mapped_column(db.Float, nullable=False)
    storage_item_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("storage_item.id"), nullable=False
    )
    storage_item: Mapped["StorageItem"] = relationship(
        "StorageItem", back_populates="nutrient"
    )
    values: Mapped[List["NutrientValue"]] = relationship(
        "NutrientValue", back_populates="nutrient", cascade="all, delete-orphan"
    )

    def __init__(
        self,
        description: str,
        unit: str,
        amount: float,
        storage_item_id: int,
        user_id: int,
    ):
        self.description = description
        self.unit = unit
        self.amount = amount
        self.storage_item_id = storage_item_id
        self.user_id = user_id


class NutrientValue(db.Model):
    __tablename__ = "nutrient_value"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(100), nullable=False)
    user_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    color: Mapped[Optional[str]] = mapped_column(db.String(50))
    nutrient_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("nutrient.id"), nullable=False
    )
    nutrient: Mapped["Nutrient"] = relationship("Nutrient", back_populates="values")
    values: Mapped[List["NutrientType"]] = relationship(
        "NutrientType", back_populates="nutrient_value", cascade="all, delete-orphan"
    )

    def __init__(self, name: str, color: Optional[str], nutrient_id: int, user_id: int):
        self.name = name
        self.color = color
        self.nutrient_id = nutrient_id
        self.user_id = user_id


class NutrientType(db.Model):
    __tablename__ = "nutrient_type"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    typ: Mapped[str] = mapped_column(db.String(50), nullable=False)
    value: Mapped[float] = mapped_column(db.Float, nullable=False)
    nutrient_value_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("nutrient_value.id"), nullable=False
    )
    nutrient_value: Mapped["NutrientValue"] = relationship(
        "NutrientValue", back_populates="values"
    )

    def __init__(self, typ: str, value: float, nutrient_value_id: int, user_id: int):
        self.typ = typ
        self.value = value
        self.nutrient_value_id = nutrient_value_id
        self.user_id = user_id


class Category(db.Model):
    __tablename__ = "category"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(db.String(100), unique=True, nullable=False)

    def __init__(self, name: str, user_id: int):
        self.name = name
        self.user_id = user_id


class StorageLocation(db.Model):
    __tablename__ = "storage_location"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(db.String(100), unique=True, nullable=False)

    def __init__(self, name: str, user_id: int):
        self.name = name
        self.user_id = user_id


class ItemUnit(db.Model):
    __tablename__ = "item_unit"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(db.String(50), unique=True, nullable=False)

    def __init__(self, name: str, user_id: int):
        self.name = name
        self.user_id = user_id


class PackageUnit(db.Model):
    __tablename__ = "package_unit"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(db.String(50), unique=True, nullable=False)

    def __init__(self, name: str, user_id: int):
        self.name = name
        self.user_id = user_id


class NutrientUnit(db.Model):
    __tablename__ = "nutrient_unit"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(db.String(50), unique=True, nullable=False)

    def __init__(self, name: str, user_id: int):
        self.name = name
        self.user_id = user_id


def get_user_group_ids(user_id):
    """Hilfsfunktion: Gibt alle Gruppen-IDs zurück, in denen der User Mitglied ist"""
    user_groups = UserGroup.query.filter_by(user_id=user_id).all()
    return [ug.group_id for ug in user_groups]


def get_group_member_ids(user_id):
    """Hilfsfunktion: Gibt alle User-IDs zurück, die in den gleichen Gruppen sind wie der aktuelle User"""
    group_ids = get_user_group_ids(user_id)
    if not group_ids:
        return [user_id]  # Nur der User selbst

    # Alle User in den gleichen Gruppen finden
    group_members = UserGroup.query.filter(UserGroup.group_id.in_(group_ids)).all()
    member_ids = list(set([gm.user_id for gm in group_members]))  # Duplikate entfernen

    # Den aktuellen User immer hinzufügen
    if user_id not in member_ids:
        member_ids.append(user_id)

    return member_ids


def generate_token(email: str, salt: str) -> str:
    ts = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    return ts.dumps(email, salt=salt)


def confirm_token(token: str, salt: str, expiration=3600) -> str:
    ts = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    return ts.loads(token, salt=salt, max_age=expiration)


import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email_smtp(recipient: str, subject: str, html_body: str) -> bool:
    sender = app.config.get("MAIL_DEFAULT_SENDER")
    smtp_server = app.config.get("MAIL_SERVER")
    smtp_port = app.config.get("MAIL_PORT")
    username = app.config.get("MAIL_USERNAME")
    password = app.config.get("MAIL_PASSWORD")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(html_body, subtype="html")

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(
            str(smtp_server), smtp_port or 0, context=context
        ) as server:
            server.login(str(username), str(password))
            server.sendmail(str(sender), recipient, msg.as_string())
        print(f"E-Mail erfolgreich an {recipient} gesendet.")
        return True
    except Exception as e:
        print("Fehler beim Versenden der E-Mail:", e)
        return False


def get_logo_base64() -> str:
    """Liest das SVG-Logo aus dem templates-Verzeichnis und kodiert es als Base64-String."""
    logo_path = os.path.join(app.root_path, "templates", "prepper-app.svg")
    with open(logo_path, "rb") as f:
        encoded_logo = base64.b64encode(f.read()).decode("utf-8")
    return encoded_logo


def send_activation_email(user: User):
    token = generate_token(user.email, salt="activate-account")
    activation_url = url_for("activate_account", token=token, _external=True)
    html = render_template(
        "activate_account_mail.html",
        activation_url=activation_url,
        username=user.username,
        logo_base64=get_logo_base64(),
        current_year=2025,  # oder dynamisch: datetime.datetime.now().year
    )
    print(html)
    try:
        # Versuche, die E-Mail zu senden, und werfe g
        send_email_smtp(user.email, "Aktivieren Sie Ihren Account", html)
    except Exception:
        print("Detaillierter Fehler:")
        print(traceback.format_exc())


def send_forgot_password_email(user: User):
    token = generate_token(user.email, salt="reset-password")
    reset_url = url_for("reset_password", token=token, _external=True)
    html = render_template(
        "forgot_password_mail.html",
        reset_url=reset_url,
        username=user.username,
        logo_base64=get_logo_base64(),
        current_year=2025,
    )
    print(html)
    try:
        send_email_smtp(user.email, "Passwort zurücksetzen", html)
    except Exception:
        print("Detaillierter Fehler:")
        print(traceback.format_exc())


def send_group_invitation_email_modern(invitation: GroupInvitation):
    """Sendet eine E-Mail-Einladung für eine Gruppe mit neuem Token-System"""
    group = invitation.group
    inviter = invitation.inviter

    # Verwende die vom Frontend bereitgestellte URL oder erstelle eine neue
    if invitation.invite_url:
        join_url = invitation.invite_url
    else:
        # Fallback: Erstelle URL mit neuem Format
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        join_url = f"{frontend_url}/invite/{invitation.invite_token}"
    print(f"Join URL: {join_url}")
    html = render_template(
        "group_invitation_mail_modern.html",  # Neues Template
        inviter_name=inviter.username,
        group_name=group.name,
        group_description=group.description,
        join_url=join_url,  # Neue URL mit /invite/:token
        invite_code=group.invite_code,  # Alter Code als Fallback
        logo_base64=get_logo_base64(),
        current_year=2025,
    )

    try:
        send_email_smtp(
            invitation.invited_email,
            f"Einladung zur Gruppe '{group.name}' - Prepper App",
            html,
        )
        print(
            f"Moderne Gruppeneinladung erfolgreich an {invitation.invited_email} gesendet."
        )
    except Exception:
        print("Detaillierter Fehler beim Senden der modernen Gruppeneinladung:")
        print(traceback.format_exc())


def send_group_invitation_email(invitation: GroupInvitation):
    """Sendet eine E-Mail-Einladung für eine Gruppe"""
    group = invitation.group
    inviter = invitation.inviter

    # Join-URL erstellen
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    join_url = f"{frontend_url}/groups/join/{invitation.invite_token}"

    html = render_template(
        "group_invitation_mail.html",
        inviter_name=inviter.username,
        group_name=group.name,
        group_description=group.description,
        join_url=join_url,
        invite_code=group.invite_code,
        logo_base64=get_logo_base64(),
        current_year=2025,
    )

    try:
        send_email_smtp(
            invitation.invited_email,
            f"Einladung zur Gruppe '{group.name}' - Prepper App",
            html,
        )
        print(f"Gruppeneinladung erfolgreich an {invitation.invited_email} gesendet.")
    except Exception:
        print("Detaillierter Fehler beim Senden der Gruppeneinladung:")
        print(traceback.format_exc())


### ROUTENDEFINITIONEN ###
## AUTHENTICATION ##
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    if (
        not data
        or "username" not in data
        or "password" not in data
        or "email" not in data
    ):
        return jsonify({"error": "Invalid input"}), 400

    # Sicherstellen, dass E-Mail noch nicht vergeben ist
    if User.query.filter_by(email=data["email"].lower()).first():
        return (
            jsonify(
                {"error": "Die E-Mail ist bereits mit einem anderen Account verknüpft."}
            ),
            409,
        )

    # Sicherstellen, dass Benutzername noch nicht vergeben ist
    if User.query.filter_by(username=data["username"]).first():
        return jsonify({"error": "Der Benutzername existiert bereits"}), 409

    user = User(username=data["username"])
    user.set_email(data["email"])
    user.set_password(data["password"])
    user.image = data.get("image") or None
    user.persons = data.get("persons") or 1
    user.activated = False  # Account zunächst inaktiv
    user.groups = []  # Keine Gruppen zu Beginn

    # Sende Aktivierungs-E-Mail
    try:
        send_activation_email(user)
    except Exception as e:
        print(e)
        return jsonify({"error": "E-Mail konnte nicht gesendet werden."}), 500

    db.session.add(user)
    db.session.commit()
    return (
        user.__to_dict__(),
        201,
    )


@app.route("/activate-account/<token>", methods=["GET"])
def activate_account(token):
    print("Aktivierungslink empfangen:", token)
    try:
        email = confirm_token(token, salt="activate-account")
    except (SignatureExpired, BadSignature):
        return jsonify({"error": "Aktivierungslink ungültig oder abgelaufen."}), 400

    user = User.query.filter_by(email=email).first_or_404()
    if not user.activated:
        user.activated = True
        db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    response = make_response(
        redirect(os.getenv("FRONTEND_URL", "http://192.168.178.79:3000"))
    )
    response.set_cookie("access_token", access_token, httponly=True, secure=True)
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=True)
    return response


@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json()
    if not data or "email" not in data:
        return jsonify({"error": "Invalid input"}), 400

    user = User.query.filter_by(email=data["email"].lower()).first()
    if not user:
        return jsonify({"error": "Kein Benutzer mit dieser E-Mail gefunden."}), 404

    send_forgot_password_email(user)
    return (
        jsonify(
            {"message": "Eine E-Mail zum Zurücksetzen des Passworts wurde gesendet."}
        ),
        200,
    )


@app.route("/reset-password/<token>", methods=["GET"])
def reset_password_form(token):
    try:
        email = confirm_token(token, salt="reset-password")
    except (SignatureExpired, BadSignature):
        return jsonify({"error": "Link ungültig oder abgelaufen."}), 400

    # Hier renderst du ein HTML-Formular, das das neue Passwort abfragt.
    # Du kannst dafür ein Template (z. B. reset_password.html) nutzen.
    return render_template("reset_password.html", token=token, email=email)


@app.route("/reset-password/<token>", methods=["POST"])
def reset_password(token):
    # Verwende request.form.to_dict() als Fallback, wenn JSON-Daten nicht vorliegen.
    data = request.form.to_dict() if request.form else (request.get_json() or {})
    if not data or "password" not in data:
        return jsonify({"error": "Invalid input"}), 400

    try:
        email = confirm_token(token, salt="reset-password")
    except (SignatureExpired, BadSignature):
        return jsonify({"error": "Link ungültig oder abgelaufen."}), 400

    user = User.query.filter_by(email=email).first_or_404()
    user.set_password(data["password"])
    db.session.commit()

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    success_url = f"{frontend_url}/resetSuccess?resetSuccess=true&message=Passwort%20erfolgreich%20zurückgesetzt."
    return redirect(success_url)


@app.route("/login", methods=["POST"])
def login():
    print("Login request received")
    data = request.get_json()
    if not data or "email" not in data or "password" not in data:
        return jsonify({"error": "Invalid input"}), 400

    user = User.query.filter_by(email=data["email"].lower()).first()
    if not user or not user.check_password(data["password"]):
        return jsonify({"error": "Falsche E-Mail oder Passwort."}), 401

    if not user.activated:
        return (
            jsonify(
                {
                    "error": "Bitte aktivieren Sie Ihren Account über den in Ihrer E-Mail enthaltenen Link."
                }
            ),
            403,
        )

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    return (
        jsonify(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "image": user.image,
                "persons": user.persons,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "isAdmin": user.admin,
                "groups": [ug.group.name for ug in user.groups],
            }
        ),
        200,
    )


@app.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    current_user = get_jwt_identity()
    new_access_token = create_access_token(identity=str(current_user))
    return jsonify(access_token=new_access_token), 200


@app.route("/user", methods=["GET"])
@jwt_required()
def get_user():
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return (
        jsonify(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email.lower(),
                "image": user.image,
                "persons": user.persons,
                "groups": [ug.group.name for ug in user.groups],
            }
        ),
        200,
    )


@app.route("/user", methods=["PUT"])
@jwt_required()
def update_user():
    user_id = get_jwt_identity()
    print(user_id)
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input data"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Aktualisiere Standardfelder
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    persons = data.get("persons")
    if username:
        user.username = username
    if email:
        user.email = email.lower()
    if password:
        user.set_password(password)
    if persons:
        user.persons = persons

    # Bild als Base64-String verarbeiten
    image_data = data.get("image")
    if image_data and isinstance(image_data, str):
        if image_data.startswith("data:image"):
            # Direkt in der Datenbank speichern (Base64-String inklusive Data-URL-Präfix)
            user.image = image_data
        else:
            return jsonify({"error": "Invalid image format"}), 400

    db.session.commit()
    return (
        jsonify(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "image": user.image,
                "persons": user.persons,
                "access_token": create_access_token(identity=str(user.id)),
                "refresh_token": create_refresh_token(identity=str(user.id)),
                "isAdmin": user.admin,
                "groups": [ug.group.name for ug in user.groups],
            }
        ),
        200,
    )


@app.route("/user", methods=["DELETE"])
@jwt_required()
def delete_user():
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User deleted successfully"}), 200


## GROUPS ##
@app.route("/groups", methods=["GET"])
@jwt_required()
def get_user_groups():
    """Alle Gruppen des Users abrufen"""
    print("Get user groups called")
    user_id = get_jwt_identity()
    user_groups = UserGroup.query.filter_by(user_id=user_id).all()

    groups_data = []
    for ug in user_groups:
        group = ug.group
        # Anzahl der Mitglieder zählen
        member_count = len(group.members)

        groups_data.append(
            {
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "image": group.image,
                "role": ug.role,
                "memberCount": member_count,
                "inviteCode": group.invite_code,
                "isCreator": group.created_by == int(user_id),
                "createdAt": group.created_at.isoformat() if group.created_at else None,
            }
        )

    return jsonify(groups_data), 200


@app.route("/groups", methods=["POST"])
@jwt_required()
def create_group():
    """Neue Gruppe erstellen"""
    user_id = get_jwt_identity()
    data = request.get_json()

    if not data or "name" not in data:
        return jsonify({"error": "Group name is required"}), 400

    # Prüfe ob eine Gruppe mit diesem Namen bereits existiert
    existing_group = Group.query.filter_by(
        name=data["name"], created_by=user_id
    ).first()
    if existing_group:
        return jsonify({"error": "Group with this name already exists"}), 409

    image = data.get("image")
    if not image or not isinstance(image, str):
        image = get_icon_as_base64("default_image.png")

    # Neue Gruppe erstellen
    new_group = Group(
        name=data["name"],
        description=data.get("description", ""),
        image=image,
        created_by=int(user_id),
    )

    db.session.add(new_group)
    db.session.flush()  # Um die group.id zu bekommen

    # Creator als Admin zur Gruppe hinzufügen
    user_group = UserGroup(user_id=int(user_id), group_id=new_group.id, role="admin")

    db.session.add(user_group)
    db.session.commit()

    return (
        jsonify(
            {
                "id": new_group.id,
                "name": new_group.name,
                "description": new_group.description,
                "image": new_group.image,
                "inviteCode": new_group.invite_code,
                "role": "admin",
                "memberCount": 1,
                "isCreator": True,
            }
        ),
        201,
    )


# gruppe bearbeiten
@app.route("/groups/<int:group_id>", methods=["PUT"])
@jwt_required()
def update_group(group_id):
    print(f"Update group called with ID: {group_id}")
    user_id = get_jwt_identity()
    group = Group.query.get_or_404(group_id)

    if group.created_by != int(user_id):
        return jsonify({"error": "Only the group creator can update the group"}), 403
    # print data aus der Anfrage
    print(f"Request data: {request}")

    data = request.get_json()
    group.name = data.get("name", group.name)
    group.description = data.get("description", group.description)

    # Bild verarbeiten (falls vorhanden)
    if "image" in data:
        image_data = data.get("image")
        if image_data and isinstance(image_data, str):
            if image_data.startswith("data:image"):
                # Validierung des Bildformats
                content_type = image_data.split(";")[0]
                if content_type in app.config["ALLOWED_CONTENT_TYPES"]:
                    # Bildgröße prüfen (Base64-String zu Bytes)
                    try:
                        import base64

                        header, encoded = image_data.split(",", 1)
                        image_bytes = base64.b64decode(encoded)
                        if len(image_bytes) <= 5 * 1024 * 1024:  # 5MB Limit
                            group.image = image_data
                        else:
                            return (
                                jsonify({"error": "Image size exceeds 5MB limit"}),
                                400,
                            )
                    except Exception:
                        return jsonify({"error": "Invalid image data"}), 400
                else:
                    return (
                        jsonify(
                            {
                                "error": "Invalid image format. Only PNG, JPG, JPEG, GIF allowed"
                            }
                        ),
                        400,
                    )
            elif image_data == "":
                # Leerer String bedeutet Bild entfernen
                group.image = None
        else:
            # None oder andere Werte bedeuten Bild entfernen
            group.image = None

    db.session.commit()

    return jsonify({"message": "Group updated successfully"}), 200


@app.route("/groups/<int:group_id>", methods=["DELETE"])
@jwt_required()
def delete_group(group_id):
    """Gruppe löschen (nur Creator)"""
    user_id = get_jwt_identity()
    print(f"User ID: {user_id}, Group ID: {group_id}")
    group = Group.query.get_or_404(group_id)

    if group.created_by != int(user_id):
        return jsonify({"error": "Only the group creator can delete the group"}), 403

    # Zuerst alle UserGroup Einträge löschen
    UserGroup.query.filter_by(group_id=group_id).delete()

    # Dann alle GroupInvitation Einträge löschen
    GroupInvitation.query.filter_by(group_id=group_id).delete()

    # Schließlich die Gruppe selbst löschen
    db.session.delete(group)
    db.session.commit()

    return jsonify({"message": "Group deleted successfully"}), 200


@app.route("/groups/<int:group_id>/members", methods=["GET"])
@jwt_required()
def get_group_members(group_id):
    """Gruppenmitglieder abrufen"""
    user_id = get_jwt_identity()

    # Prüfe ob User Mitglied der Gruppe ist
    user_group = UserGroup.query.filter_by(user_id=user_id, group_id=group_id).first()
    if not user_group:
        return jsonify({"error": "You are not a member of this group"}), 403

    members = UserGroup.query.filter_by(group_id=group_id).all()

    members_data = []
    for member in members:
        user = User.query.get(member.user_id)
        if user:  # Null-Prüfung hinzufügen
            members_data.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": member.role,
                    "joinedAt": (
                        member.joined_at.isoformat() if member.joined_at else None
                    ),
                }
            )

    return jsonify(members_data), 200


@app.route("/groups/join/<invite_code>", methods=["POST"])
@jwt_required()
def join_group_by_code(invite_code):
    """Gruppe über Einladungscode beitreten"""
    user_id = get_jwt_identity()

    group = Group.query.filter_by(invite_code=invite_code).first()
    if not group:
        return jsonify({"error": "Invalid invite code"}), 404

    # Prüfe ob User bereits Mitglied ist
    existing_membership = UserGroup.query.filter_by(
        user_id=user_id, group_id=group.id
    ).first()
    if existing_membership:
        return jsonify({"error": "You are already a member of this group"}), 409

    # User zur Gruppe hinzufügen
    user_group = UserGroup(user_id=int(user_id), group_id=group.id, role="member")

    db.session.add(user_group)
    db.session.commit()

    return (
        jsonify(
            {
                "message": f"Successfully joined group '{group.name}'",
                "group": {
                    "id": group.id,
                    "name": group.name,
                    "description": group.description,
                    "image": group.image,
                    "role": "member",
                },
            }
        ),
        200,
    )


@app.route("/groups/<int:group_id>/generate-invite-token", methods=["POST"])
@jwt_required()
def generate_invite_token(group_id):
    """Generiert einen Invite-Token für eine Gruppe - Für Link-Sharing ohne E-Mail"""
    user_id = get_jwt_identity()

    print(f"Generate invite token called for group {group_id} by user {user_id}")

    # Prüfe ob User Mitglied der Gruppe ist
    user_group = UserGroup.query.filter_by(user_id=user_id, group_id=group_id).first()
    if not user_group:
        return jsonify({"error": "You are not a member of this group"}), 403

    # Hole die Gruppe
    group = Group.query.get_or_404(group_id)

    # ✅ KEINE Prüfung ob User bereits Mitglied ist - das ist für Link-Sharing gedacht
    # ✅ Auch bestehende Gruppenmitglieder können Links generieren

    # Erstelle neuen Invite-Token (ohne E-Mail)
    invitation = GroupInvitation(
        group_id=group_id,
        invited_by=int(user_id),
        invited_email="",  # Leer für Token-only Generation
        invite_token="",  # Wird automatisch generiert
        invite_url="",  # Wird vom Frontend gesetzt
    )

    db.session.add(invitation)
    db.session.commit()

    print(f"Generated invite token: {invitation.invite_token}")

    return (
        jsonify(
            {
                "message": "Invite token generated successfully",
                "inviteToken": invitation.invite_token,
                "expiresAt": invitation.expires_at,
                "groupName": group.name,
            }
        ),
        201,
    )


@app.route("/groups/<int:group_id>/invite", methods=["POST"])
@jwt_required()
def invite_to_group(group_id):
    print(f"Invite to group called with ID: {group_id}")
    """User per E-Mail zur Gruppe einladen - Erweitert für neues Token-System"""
    user_id = get_jwt_identity()
    data = request.get_json()

    if not data or "invitedEmail" not in data:
        return jsonify({"error": "Email is required"}), 400

    # Prüfe ob User Admin/Creator der Gruppe ist
    user_group = UserGroup.query.filter_by(user_id=user_id, group_id=group_id).first()
    if not user_group or user_group.role not in ["admin", "creator"]:
        return jsonify({"error": "Only group admins can invite users"}), 403

    group = Group.query.get_or_404(group_id)
    invited_email = data["invitedEmail"].lower()

    # Neue Token-System Integration
    invite_token = data.get("inviteToken")  # Token vom Frontend
    invite_url = data.get("inviteUrl")  # Vollständige URL vom Frontend

    # Prüfe ob bereits eine aktive Einladung existiert
    existing_invite = GroupInvitation.query.filter_by(
        group_id=group_id, invited_email=invited_email, status="pending"
    ).first()

    if existing_invite:
        return jsonify({"error": "Invitation already sent to this email"}), 409

    # Prüfe ob User bereits Mitglied ist
    invited_user = User.query.filter_by(email=invited_email).first()
    if invited_user:
        existing_membership = UserGroup.query.filter_by(
            user_id=invited_user.id, group_id=group_id
        ).first()
        if existing_membership:
            return jsonify({"error": "User is already a member of this group"}), 409

    # Neue Einladung erstellen mit Token-System
    invitation = GroupInvitation(
        group_id=group_id,
        invited_by=int(user_id),
        invited_email=invited_email,
        invite_token=invite_token,  # Verwende Frontend-Token
        invite_url=invite_url,  # Verwende Frontend-URL
    )

    db.session.add(invitation)
    db.session.commit()

    # E-Mail senden mit neuer URL
    try:
        send_group_invitation_email_modern(invitation)
    except Exception as e:
        print(f"Fehler beim Senden der Einladungs-E-Mail: {e}")

    return (
        jsonify(
            {
                "message": f"Invitation sent to {invited_email}",
                "inviteToken": invitation.invite_token,
            }
        ),
        201,
    )


@app.route("/groups/join-invitation/<invite_token>", methods=["POST"])
@jwt_required()
def join_group_via_invitation(invite_token):
    """Tritt einer Gruppe über Einladungstoken bei - Für Frontend-Integration"""
    user_id = get_jwt_identity()

    print(f"User {user_id} versucht, über Token {invite_token} beizutreten")

    invitation = GroupInvitation.query.filter_by(invite_token=invite_token).first()

    if not invitation:
        print(f"Token {invite_token} nicht gefunden")
        return jsonify({"error": "Invalid invitation token"}), 404

    if invitation.status != "pending":
        print(f"Token {invite_token} nicht mehr gültig - Status: {invitation.status}")
        return jsonify({"error": "Invitation is no longer valid"}), 400

    if invitation.expires_at and invitation.expires_at < datetime.utcnow():
        print(f"Token {invite_token} abgelaufen")
        return jsonify({"error": "Invitation has expired"}), 400

    # Hole die Gruppe
    group = invitation.group

    # Prüfe ob User bereits in der Gruppe ist
    existing_membership = UserGroup.query.filter_by(
        group_id=group.id, user_id=user_id
    ).first()

    if existing_membership:
        print(f"User {user_id} ist bereits Mitglied der Gruppe {group.id}")
        return jsonify({"error": "You are already a member of this group"}), 409

    # Erstelle neue Gruppenmitgliedschaft
    user_group = UserGroup(user_id=int(user_id), group_id=group.id, role="member")

    # Markiere Einladung als akzeptiert
    invitation.status = "accepted"
    invitation.accepted_at = datetime.utcnow()

    db.session.add(user_group)
    db.session.commit()

    print(f"User {user_id} erfolgreich der Gruppe {group.name} hinzugefügt")

    return (
        jsonify(
            {
                "success": True,
                "message": f"Successfully joined group '{group.name}'",
                "group": {
                    "id": group.id,
                    "name": group.name,
                    "description": group.description,
                    "image": group.image,
                    "role": "member",
                },
            }
        ),
        200,
    )


@app.route("/groups/validate-invitation/<invite_token>", methods=["GET"])
def validate_invitation_token(invite_token):
    """Validiert einen Einladungstoken ohne Login (für Frontend)"""
    print(f"Validating invitation token: {invite_token}")
    invitation = GroupInvitation.query.filter_by(invite_token=invite_token).first()

    if not invitation:
        print(f"Token {invite_token} nicht gefunden")
        return jsonify({"error": "Invalid invitation token"}), 404

    if invitation.status != "pending":
        print(f"Token {invite_token} nicht mehr gültig - Status: {invitation.status}")
        return jsonify({"error": "Invitation is no longer valid"}), 400

    if invitation.expires_at and invitation.expires_at < datetime.utcnow():
        print(f"Token {invite_token} abgelaufen")
        return jsonify({"error": "Invitation has expired"}), 400

    group = invitation.group
    inviter = invitation.inviter

    return (
        jsonify(
            {
                "valid": True,
                "groupId": group.id,
                "groupName": group.name,
                "groupDescription": group.description,
                "inviterName": inviter.username,
                "expiresAt": (
                    invitation.expires_at.isoformat() if invitation.expires_at else None
                ),
            }
        ),
        200,
    )


# route zum entfernen von benutzern
@app.route("/groups/<int:group_id>/remove/<int:user_id>", methods=["POST"])
@jwt_required()
def remove_user_from_group(group_id, user_id):
    """Entfernt einen User aus der Gruppe (nur Admins)"""
    current_user_id = get_jwt_identity()

    # Prüfe ob User Admin/Creator der Gruppe ist
    user_group = UserGroup.query.filter_by(
        user_id=current_user_id, group_id=group_id
    ).first()
    if not user_group or user_group.role not in ["admin", "creator"]:
        return jsonify({"error": "Only group admins can remove users"}), 403

    # Prüfe ob der zu entfernende User in der Gruppe ist
    user_to_remove = UserGroup.query.filter_by(
        user_id=user_id, group_id=group_id
    ).first()
    if not user_to_remove:
        return jsonify({"error": "User is not a member of this group"}), 404

    db.session.delete(user_to_remove)
    db.session.commit()

    return jsonify({"message": f"User {user_id} removed from group {group_id}"}), 200


@app.route("/groups/<int:group_id>/leave", methods=["POST"])
@jwt_required()
def leave_group(group_id):
    """Gruppe verlassen"""
    user_id = get_jwt_identity()

    user_group = UserGroup.query.filter_by(user_id=user_id, group_id=group_id).first()
    if not user_group:
        return jsonify({"error": "You are not a member of this group"}), 404

    group = Group.query.get_or_404(group_id)

    # Creator kann die Gruppe nicht verlassen, muss sie löschen
    if group.created_by == int(user_id):
        return (
            jsonify(
                {
                    "error": "Group creator cannot leave the group. Delete the group instead."
                }
            ),
            400,
        )

    db.session.delete(user_group)
    db.session.commit()

    return jsonify({"message": "Successfully left the group"}), 200


## BASKET ##
@app.route("/basket", methods=["GET"])
@jwt_required()
def get_basket():
    user_id = get_jwt_identity()

    # Alle User-IDs von Gruppenmitgliedern abrufen
    accessible_user_ids = get_group_member_ids(int(user_id))
    items = (
        db.session.query(BasketItem)
        .filter(BasketItem.user_id.in_(accessible_user_ids))
        .all()
    )
    return (
        jsonify(
            [
                {
                    "id": item.id,
                    "name": item.name,
                    "amount": item.amount,
                    "categories": item.categories.split(",") if item.categories else [],
                    "icon": item.icon,
                }
                for item in items
            ]
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/basket", methods=["POST"])
@jwt_required()
def add_basket_item():
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input data"}), 400

    item = (
        db.session.query(BasketItem)
        .filter_by(name=data["name"], user_id=user_id)
        .first()
    )
    if item is None:
        item = BasketItem(
            name=data["name"],
            amount=1,
            categories=",".join(data.get("categories", [])),
            icon=data.get("icon"),
            user_id=user_id,
        )
        db.session.add(item)
    else:
        item.amount = item.amount + 1

    db.session.commit()
    # rückgabe des datensatzes als bestätigung
    return (
        jsonify(
            {
                "id": item.id,
                "name": item.name,
                "amount": item.amount,
                "categories": item.categories.split(",") if item.categories else [],
                "icon": item.icon,
            }
        ),
        201,
    )


@app.route("/basket/<int:item_id>", methods=["PUT"])
@jwt_required()
def update_basket_item(item_id):
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input data"}), 400

    item = db.session.get(BasketItem, item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    # Prüfen ob der User berechtigt ist (Besitzer oder Gruppenmitglied)
    accessible_user_ids = get_group_member_ids(int(user_id))
    if item.user_id not in accessible_user_ids:
        return jsonify({"error": "Unauthorized"}), 403

    # increase amount
    item.amount = data["amount"]
    if "categories" in data:
        item.categories = ",".join(data.get("categories", []))
    item.icon = data.get("icon")
    item.name = data.get("name")

    if int(item.amount) < 1:
        db.session.delete(item)
    db.session.commit()
    return (
        jsonify(
            {
                "id": item.id,
                "name": item.name,
                "amount": item.amount,
                "categories": item.categories.split(",") if item.categories else [],
                "icon": item.icon,
            }
        ),
        201,
    )


@app.route("/basket/<int:item_id>", methods=["DELETE"])
@jwt_required()
def delete_basket_item(item_id):
    user_id = get_jwt_identity()
    item = db.session.get(BasketItem, item_id)
    print(f"Item: {item} - User: {user_id}")
    if not item:
        return jsonify({"error": "Item not found"}), 404

    # Prüfen ob der User berechtigt ist (Besitzer oder Gruppenmitglied)
    accessible_user_ids = get_group_member_ids(int(user_id))
    if item.user_id not in accessible_user_ids:
        return jsonify({"error": "Unauthorized"}), 403

    print("Delete item")
    db.session.delete(item)
    print("Commit")
    db.session.commit()
    print("Return")
    return (
        jsonify(
            {
                "id": item.id,
                "name": item.name,
                "amount": 0,
                "categories": item.categories.split(",") if item.categories else [],
                "icon": item.icon,
            }
        ),
        200,
    )


@app.route("/items/bulk", methods=["POST"])
@jwt_required()
def add_bulk_items():
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input data"}), 400

    # Überprüfe die notwendigen Felder und sammle Mappings für StorageItem
    mappings = []
    for item_data in data:
        required_keys = [
            "name",
            "amount",
            "unit",
            "storageLocation",
            "lowestAmount",
            "midAmount",
        ]
        if not all(key in item_data and item_data[key] != "" for key in required_keys):
            return jsonify({"error": "Invalid input data for one or more items"}), 400

        mapping = {
            "name": item_data["name"],
            "amount": item_data["amount"],
            "categories": ",".join(item_data.get("categories", [])),
            "lowestAmount": item_data["lowestAmount"],
            "midAmount": item_data["midAmount"],
            "unit": item_data["unit"],
            "packageQuantity": item_data.get("packageQuantity"),
            "packageUnit": item_data.get("packageUnit"),
            "storageLocation": item_data["storageLocation"],
            "icon": item_data.get("icon"),
            "user_id": user_id,
        }
        # Wenn kein Icon vorhanden, versuche es über SerpAPI zu ermitteln
        if not mapping["icon"]:
            mapping["icon"] = get_icon_from_serpapi(mapping["name"])
        mappings.append(mapping)

    # Phase 1: Bulk-Insert für StorageItem
    mapper: Mapper = cast(Mapper, inspect(StorageItem))
    db.session.bulk_insert_mappings(mapper, mappings)

    db.session.commit()

    # Phase 2: Verarbeite Nutrient-Daten für jedes Item
    for item_data in data:
        new_item = StorageItem.query.filter_by(
            name=item_data["name"],
            storageLocation=item_data["storageLocation"],
            unit=item_data["unit"],
            user_id=user_id,
        ).first()
        if new_item is None:
            return jsonify({"error": f"Item {item_data['name']} not found."}), 404

        if "nutrients" in item_data and item_data["nutrients"]:
            nutrient_data = item_data["nutrients"]
            nutrient = Nutrient(
                description=nutrient_data["description"],
                unit=nutrient_data["unit"],
                amount=nutrient_data["amount"],
                storage_item_id=new_item.id,
                user_id=user_id,
            )
            db.session.add(nutrient)
            db.session.flush()  # Zuweisung der nutrient.id

            for value_data in nutrient_data.get("values", []):
                nutrient_value = NutrientValue(
                    name=value_data["name"],
                    color=value_data.get("color"),
                    nutrient_id=nutrient.id,
                    user_id=user_id,
                )
                db.session.add(nutrient_value)
                db.session.flush()  # nutrient_value.id zuweisen

                for type_data in value_data.get("values", []):
                    nutrient_type = NutrientType(
                        typ=type_data["typ"],
                        value=type_data["value"],
                        nutrient_value_id=nutrient_value.id,
                        user_id=user_id,
                    )
                    db.session.add(nutrient_type)

    db.session.commit()
    return jsonify({"message": "Items added successfully"}), 201


## ITEMS ##
@app.route("/items", methods=["GET"])
@jwt_required()
def get_items():
    user_id = get_jwt_identity()
    searchstring = request.args.get("q", "")

    # Alle User-IDs aus den gleichen Gruppen holen
    accessible_user_ids = get_group_member_ids(int(user_id))

    query = StorageItem.query.filter(StorageItem.user_id.in_(accessible_user_ids))

    if searchstring:
        from sqlalchemy import func

        query = query.filter(
            func.lower(StorageItem.name).like(f"%{searchstring.lower()}%")
        )

    items = query.all()

    return (
        jsonify(
            [
                {
                    "id": item.id,
                    "name": item.name,
                    "amount": item.amount,
                    "categories": item.categories.split(",") if item.categories else [],
                    "lowestAmount": item.lowestAmount,
                    "midAmount": item.midAmount,
                    "unit": item.unit,
                    "packageQuantity": item.packageQuantity,
                    "packageUnit": item.packageUnit,
                    "storageLocation": item.storageLocation,
                    "icon": item.icon,
                    "owner": item.user.username,  # Zeige den Besitzer des Items
                    "isOwner": item.user_id
                    == int(user_id),  # Zeige ob der aktuelle User der Besitzer ist
                    "nutrients": (
                        {
                            "id": item.nutrient.id,
                            "description": item.nutrient.description,
                            "unit": item.nutrient.unit,
                            "amount": item.nutrient.amount,
                            "values": [
                                {
                                    "id": v.id,
                                    "name": v.name,
                                    "color": v.color,
                                    "values": [
                                        {"typ": t.typ, "value": t.value}
                                        for t in v.values
                                    ],
                                }
                                for v in item.nutrient.values
                            ],
                        }
                        if item.nutrient
                        else None
                    ),
                }
                for item in items
            ]
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/items", methods=["POST"])
@jwt_required()
def add_item():
    user_id = get_jwt_identity()
    data = request.get_json()
    if (
        not data
        or "name" not in data
        or "amount" not in data
        or "unit" not in data
        or data["name"] == ""
        or data["amount"] == ""
        or data["unit"] == ""
    ):
        return jsonify({"error": "Invalid input data"}), 400

    duplicate_item = StorageItem.query.filter_by(
        name=data["name"],
        unit=data["unit"],
        user_id=user_id,
    ).first()
    if duplicate_item:
        return (
            jsonify(
                {
                    "error": "Item with the same name, storageLocation, and unit already exists."
                }
            ),
            409,
        )

    new_item = StorageItem(
        name=data["name"],
        amount=data["amount"],
        categories=",".join(data.get("categories", [])),
        lowestAmount=data["lowestAmount"],
        midAmount=data["midAmount"],
        unit=data["unit"],
        packageQuantity=data.get("packageQuantity"),
        packageUnit=data.get("packageUnit"),
        storageLocation=data["storageLocation"],
        icon=data.get("icon"),
        user_id=user_id,
    )

    if not new_item.icon or new_item.icon == "":
        # setze prepper-app.svg als Standard-Icon in base64
        new_item.icon = get_icon_as_base64("default_image.png")

    db.session.add(new_item)
    db.session.flush()  # new_item.id verfügbar

    if "nutrients" in data and data["nutrients"]:
        nutrient_data = data["nutrients"]
        nutrient = Nutrient(
            description=nutrient_data["description"],
            unit=nutrient_data["unit"],
            amount=nutrient_data["amount"],
            storage_item_id=new_item.id,
            user_id=user_id,
        )
        db.session.add(nutrient)
        db.session.flush()
        for value_data in nutrient_data.get("values", []):
            nutrient_value = NutrientValue(
                name=value_data["name"],
                color=value_data.get("color"),
                nutrient_id=nutrient.id,
                user_id=user_id,
            )
            db.session.add(nutrient_value)
            db.session.flush()
            for type_data in value_data.get("values", []):
                nutrient_type = NutrientType(
                    typ=type_data["typ"],
                    value=type_data["value"],
                    nutrient_value_id=nutrient_value.id,
                    user_id=user_id,
                )
                db.session.add(nutrient_type)
    db.session.commit()
    return (
        jsonify(
            {
                "id": new_item.id,
                "name": new_item.name,
                "amount": new_item.amount,
                "categories": (
                    new_item.categories.split(",") if new_item.categories else []
                ),
                "lowestAmount": new_item.lowestAmount,
                "midAmount": new_item.midAmount,
                "unit": new_item.unit,
                "packageQuantity": new_item.packageQuantity,
                "packageUnit": new_item.packageUnit,
                "storageLocation": new_item.storageLocation,
                "icon": new_item.icon,
                "nutrients": (
                    {
                        "id": new_item.nutrient.id,
                        "description": new_item.nutrient.description,
                        "unit": new_item.nutrient.unit,
                        "amount": new_item.nutrient.amount,
                        "values": [
                            {
                                "id": v.id,
                                "name": v.name,
                                "color": v.color,
                                "values": [
                                    {"typ": t.typ, "value": t.value} for t in v.values
                                ],
                            }
                            for v in new_item.nutrient.values
                        ],
                    }
                    if new_item.nutrient
                    else None
                ),
            }
        ),
        201,
    )


@app.route("/items/<int:item_id>", methods=["PUT"])
@jwt_required()
def update_item(item_id):
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input data"}), 400

    item = db.session.get(StorageItem, item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    # Prüfen ob der User berechtigt ist (Besitzer oder Gruppenmitglied)
    accessible_user_ids = get_group_member_ids(int(user_id))
    if item.user_id not in accessible_user_ids:
        return jsonify({"error": "Unauthorized"}), 403

    item.name = data.get("name", item.name)
    item.amount = data.get("amount", item.amount)
    if "categories" in data:
        item.categories = ",".join(data.get("categories", []))
    item.lowestAmount = data.get("lowestAmount", item.lowestAmount)
    item.midAmount = data.get("midAmount", item.midAmount)
    item.unit = data.get("unit", item.unit)
    item.packageQuantity = data.get("packageQuantity", item.packageQuantity)
    item.packageUnit = data.get("packageUnit", item.packageUnit)
    item.storageLocation = data.get("storageLocation", item.storageLocation)
    item.icon = data.get("icon", item.icon)

    if item.icon and item.icon != "" and isinstance(item.icon, str):
        try:
            header, encoded = item.icon.split(",", 1)  # type: ignore
        except ValueError:
            return (
                jsonify(
                    {
                        "error": "Ungültige Bilddaten: Das Bildformat konnte nicht verarbeitet werden."
                    }
                ),
                400,
            )

        content_type = header.split(";")[0]
        if content_type not in app.config["ALLOWED_CONTENT_TYPES"]:
            return (
                jsonify(
                    {
                        "error": "Ungültiges Bildformat: Es sind nur PNG-, JPG-, JPEG- oder GIF-Dateien erlaubt."
                    }
                ),
                400,
            )

        try:
            image_data = base64.b64decode(encoded)
        except Exception as e:
            return jsonify({"error": "Fehler beim Dekodieren der Bilddaten."}), 400

        if len(image_data) > 5 * 1024 * 1024:
            return (
                jsonify(
                    {
                        "error": "Die Bildgröße überschreitet das erlaubte Limit von 5 MB."
                    }
                ),
                400,
            )

    db.session.commit()
    return (
        jsonify(
            {
                "id": item.id,
                "name": item.name,
                "amount": item.amount,
                "categories": item.categories.split(",") if item.categories else [],
                "lowestAmount": item.lowestAmount,
                "midAmount": item.midAmount,
                "unit": item.unit,
                "packageQuantity": item.packageQuantity,
                "packageUnit": item.packageUnit,
                "storageLocation": item.storageLocation,
                "icon": item.icon,
                "nutrients": (
                    {
                        "id": item.nutrient.id,
                        "description": item.nutrient.description,
                        "unit": item.nutrient.unit,
                        "amount": item.nutrient.amount,
                        "values": [
                            {
                                "id": v.id,
                                "name": v.name,
                                "color": v.color,
                                "values": [
                                    {"typ": t.typ, "value": t.value} for t in v.values
                                ],
                            }
                            for v in item.nutrient.values
                        ],
                    }
                    if item.nutrient
                    else None
                ),
            }
        ),
        200,
    )


@app.route("/items/<int:item_id>", methods=["GET"])
@jwt_required()
def get_item(item_id):
    user_id = get_jwt_identity()
    item = StorageItem.query.filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Item not found"}), 404

    # Prüfen ob der User berechtigt ist (Besitzer oder Gruppenmitglied)
    accessible_user_ids = get_group_member_ids(int(user_id))
    if item.user_id not in accessible_user_ids:
        return jsonify({"error": "Unauthorized"}), 403
    return (
        jsonify(
            {
                "id": item.id,
                "name": item.name,
                "amount": item.amount,
                "categories": item.categories.split(",") if item.categories else [],
                "lowestAmount": item.lowestAmount,
                "midAmount": item.midAmount,
                "unit": item.unit,
                "packageQuantity": item.packageQuantity,
                "packageUnit": item.packageUnit,
                "storageLocation": item.storageLocation,
                "icon": item.icon,
                "nutrients": (
                    {
                        "id": item.nutrient.id,
                        "description": item.nutrient.description,
                        "unit": item.nutrient.unit,
                        "amount": item.nutrient.amount,
                        "values": [
                            {
                                "id": v.id,
                                "name": v.name,
                                "color": v.color,
                                "values": [
                                    {"typ": t.typ, "value": t.value} for t in v.values
                                ],
                            }
                            for v in item.nutrient.values
                        ],
                    }
                    if item.nutrient
                    else None
                ),
            }
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/items/<int:item_id>", methods=["DELETE"])
@jwt_required()
def delete_item(item_id):
    user_id = get_jwt_identity()
    item = StorageItem.query.filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Fehler beim Löschen des Items"}), 404

    # Prüfen ob der User berechtigt ist (Besitzer oder Gruppenmitglied)
    accessible_user_ids = get_group_member_ids(int(user_id))
    if item.user_id not in accessible_user_ids:
        return (
            jsonify({"error": "Sie sind nicht berechtigt, dieses Item zu löschen"}),
            403,
        )

    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "Item deleted successfully"}), 200


## NUTRIENTS ##
@app.route("/items/<int:item_id>/nutrients", methods=["PUT"])
@jwt_required()
def update_nutrients(item_id):
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input data"}), 400

    nutrient_data = data
    item = StorageItem.query.filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Item not found"}), 404

    # Prüfen ob der User berechtigt ist (Besitzer oder Gruppenmitglied)
    accessible_user_ids = get_group_member_ids(int(user_id))
    if item.user_id not in accessible_user_ids:
        return jsonify({"error": "Unauthorized"}), 403

    nutrient = item.nutrient

    if nutrient is None:
        nutrient = Nutrient(
            description=nutrient_data.get("description", ""),
            unit=nutrient_data.get("unit", ""),
            amount=nutrient_data.get("amount", 0.0),
            storage_item_id=item.id,
            user_id=user_id,
        )
        db.session.add(nutrient)
        db.session.flush()
    else:
        nutrient.description = nutrient_data.get("description", nutrient.description)
        nutrient.unit = nutrient_data.get("unit", nutrient.unit)
        nutrient.amount = nutrient_data.get("amount", nutrient.amount)

        for nv in list(nutrient.values):
            db.session.delete(nv)
        db.session.flush()

    incoming_values = nutrient_data.get("values", [])
    for value_data in incoming_values:
        nv = NutrientValue(
            name=value_data["name"],
            color=value_data.get("color"),
            nutrient_id=nutrient.id,
            user_id=user_id,
        )
        db.session.add(nv)
        db.session.flush()
        for type_data in value_data.get("values", []):
            nt = NutrientType(
                typ=type_data["typ"],
                value=type_data["value"],
                nutrient_value_id=nv.id,
                user_id=user_id,
            )
            db.session.add(nt)

    db.session.commit()
    return (
        jsonify(
            {
                "id": item.id,
                "name": item.name,
                "amount": item.amount,
                "categories": item.categories.split(",") if item.categories else [],
                "lowestAmount": item.lowestAmount,
                "midAmount": item.midAmount,
                "unit": item.unit,
                "packageQuantity": item.packageQuantity,
                "packageUnit": item.packageUnit,
                "storageLocation": item.storageLocation,
                "icon": item.icon,
                "nutrients": (
                    {
                        "id": nutrient.id,
                        "description": nutrient.description,
                        "unit": nutrient.unit,
                        "amount": nutrient.amount,
                        "values": [
                            {
                                "id": v.id,
                                "name": v.name,
                                "color": v.color,
                                "values": [
                                    {"typ": t.typ, "value": t.value} for t in v.values
                                ],
                            }
                            for v in item.nutrient.values
                        ],
                    }
                    if item.nutrient
                    else None
                ),
            }
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/categories", methods=["GET"])
@jwt_required()
def get_categories():
    user_id = get_jwt_identity()
    default_user = User.query.filter_by(username=os.getenv("DEFAULT_USERNAME")).first()
    default_user_id = default_user.id if default_user else None

    categories = (
        db.session.query(Category)
        .filter((Category.user_id == user_id) | (Category.user_id == default_user_id))
        .all()
    )
    return jsonify([{"id": cat.id, "name": cat.name} for cat in categories]), 200


@app.route("/storage-locations", methods=["GET"])
@jwt_required()
def get_storage_locations():
    user_id = get_jwt_identity()
    default_user = User.query.filter_by(username=os.getenv("DEFAULT_USERNAME")).first()
    default_user_id = default_user.id if default_user else None

    locations = (
        db.session.query(StorageLocation)
        .filter(
            (StorageLocation.user_id == user_id)
            | (StorageLocation.user_id == default_user_id)
        )
        .all()
    )
    return jsonify([{"id": loc.id, "name": loc.name} for loc in locations]), 200


@app.route("/item-units", methods=["GET"])
@jwt_required()
def get_item_units():
    user_id = get_jwt_identity()
    default_user = User.query.filter_by(username=os.getenv("DEFAULT_USERNAME")).first()
    default_user_id = default_user.id if default_user else None

    units = (
        db.session.query(ItemUnit)
        .filter((ItemUnit.user_id == user_id) | (ItemUnit.user_id == default_user_id))
        .all()
    )
    return jsonify([{"id": unit.id, "name": unit.name} for unit in units]), 200


@app.route("/package-units", methods=["GET"])
@jwt_required()
def get_package_units():
    user_id = get_jwt_identity()
    default_user = User.query.filter_by(username=os.getenv("DEFAULT_USERNAME")).first()
    default_user_id = default_user.id if default_user else None

    packages = (
        db.session.query(PackageUnit)
        .filter(
            (PackageUnit.user_id == user_id) | (PackageUnit.user_id == default_user_id)
        )
        .all()
    )
    return (
        jsonify([{"id": package.id, "name": package.name} for package in packages]),
        200,
    )


@app.route("/nutrient-units", methods=["GET"])
@jwt_required()
def get_nutrient_units():
    user_id = get_jwt_identity()
    default_user = User.query.filter_by(username=os.getenv("DEFAULT_USERNAME")).first()
    default_user_id = default_user.id if default_user else None

    nutrients = (
        db.session.query(NutrientUnit)
        .filter(
            (NutrientUnit.user_id == user_id)
            | (NutrientUnit.user_id == default_user_id)
        )
        .all()
    )
    return (
        jsonify([{"id": nutrient.id, "name": nutrient.name} for nutrient in nutrients]),
        200,
    )


# function to search for an image of the item on bing
def get_icon_from_serpapi(name):
    params = {
        "engine": "google_images",
        "q": name,
        "api_key": os.getenv("SEARCH_API_KEY"),
    }
    try:
        search = serpapi.search(params)
        return search["images_results"][0].get("thumbnail")
    except HTTPError as e:
        return ""


def get_icon_as_base64(filename):
    # Wenn kein absoluter Pfad angegeben, suche im templates Ordner
    if not os.path.isabs(filename):
        filepath = os.path.join(app.root_path, "templates", filename)
    else:
        filepath = filename

    try:
        with open(filepath, "rb") as image_file:
            file_data = image_file.read()
            base64_string = base64.b64encode(file_data).decode("utf-8")

            # Bestimme den MIME-Type basierend auf der Dateiendung
            _, ext = os.path.splitext(filepath.lower())
            if ext == ".svg":
                mime_type = "image/svg+xml"
            elif ext in [".jpg", ".jpeg"]:
                mime_type = "image/jpeg"
            elif ext == ".png":
                mime_type = "image/png"
            elif ext == ".gif":
                mime_type = "image/gif"
            else:
                mime_type = "image/png"  # Fallback

            # Returniere als Data-URL Format
            return f"data:{mime_type};base64,{base64_string}"
    except FileNotFoundError:
        print(f"Icon-Datei nicht gefunden: {filepath}")
        return ""


## HEALTH CHECK ##
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint zur Diagnose von Datenbankproblemen"""
    try:
        # Test Datenbankverbindung
        db.session.execute(db.text("SELECT 1"))
        return (
            jsonify(
                {
                    "status": "healthy",
                    "database": "connected",
                    "database_uri": app.config["SQLALCHEMY_DATABASE_URI"],
                }
            ),
            200,
        )
    except Exception as e:
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "database": "disconnected",
                    "error": str(e),
                    "database_uri": app.config["SQLALCHEMY_DATABASE_URI"],
                }
            ),
            500,
        )


if __name__ == "__main__":
    with app.app_context():
        try:
            # Test database connection first
            db.session.execute(db.text("SELECT 1"))
            print("Database connection successful")

            # Create tables
            db.create_all()
            print("Database tables created/verified")

        except Exception as e:
            print(f"Database initialization error: {e}")
            print(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
            print(f"Current working directory: {os.getcwd()}")

            # Try to provide helpful debugging information
            if "sqlite:///" in app.config["SQLALCHEMY_DATABASE_URI"]:
                db_path = app.config["SQLALCHEMY_DATABASE_URI"][10:]
                db_dir = os.path.dirname(db_path) if db_path else "."
                print(f"Database file path: {db_path}")
                print(f"Database directory: {db_dir}")
                print(
                    f"Directory exists: {os.path.exists(db_dir) if db_dir != '.' else True}"
                )
                print(
                    f"Directory writable: {os.access(db_dir, os.W_OK) if db_dir != '.' and os.path.exists(db_dir) else 'Unknown'}"
                )

            raise

    # Nur im Development-Modus mit debug=True starten
    # In Produktion wird Gunicorn verwendet
    if os.getenv("FLASK_ENV") == "development":
        app.run(debug=True, host="0.0.0.0", port=5000)
    else:
        print("App initialized successfully for production")

# Für Gunicorn: App-Objekt exportieren
application = app
