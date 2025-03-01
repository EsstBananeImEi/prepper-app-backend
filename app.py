import base64
from email.header import Header
from functools import lru_cache
import os
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
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///storage.db"
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

app_url = os.getenv("APP_URL") or "http://localhost:5000"

# Swagger initialisieren
with open("swagger.yaml", "r") as f:
    swagger_template = yaml.safe_load(f)
    swagger_template["host"] = app_url.split("://")[1]
    swagger_template["schemes"] = [app_url.split("://")[0]]

swagger = Swagger(app, template=swagger_template)
jwt = JWTManager(app)
mail = Mail(app)
db = SQLAlchemy(app)


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


### Hilfsfunktionen ###


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

    # Sende Aktivierungs-E-Mail
    try:
        send_activation_email(user)
    except Exception as e:
        print(e)
        return jsonify({"error": "E-Mail konnte nicht gesendet werden."}), 500

    db.session.add(user)
    db.session.commit()
    return (
        jsonify(
            {
                "message": "Registrierung erfolgreich. Bitte aktivieren Sie Ihren Account über den in Ihrer E-Mail enthaltenen Link."
            }
        ),
        201,
    )


@app.route("/activate-account/<token>", methods=["GET"])
def activate_account(token):
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

    # Hole die Frontend-URL aus den Umgebungsvariablen (oder verwende einen Standardwert)
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    # Baue eine URL, z. B. /reset-success, die eine Erfolgsmeldung über Query-Parameter erhält
    success_url = f"{frontend_url}/resetSuccess?resetSuccess=true&message=Passwort%20erfolgreich%20zurückgesetzt."
    return redirect(success_url)


@app.route("/login", methods=["POST"])
def login():
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


## BASKET ##
@app.route("/basket", methods=["GET"])
@jwt_required()
def get_basket():
    user_id = get_jwt_identity()
    items = db.session.query(BasketItem).filter_by(user_id=user_id).all()
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
    if not item or str(item.user_id) != user_id:
        return jsonify({"error": "Item not found or unauthorized"}), 404

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
    if not item or str(item.user_id) != user_id:
        return jsonify({"error": "Item not found or unauthorized"}), 404
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
    query = StorageItem.query.filter_by(user_id=user_id)

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
        new_item.icon = get_icon_from_serpapi(new_item.name)

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
    if not item or str(item.user_id) != user_id:
        return jsonify({"error": "Item not found or unauthorized"}), 404

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
    item = StorageItem.query.filter_by(id=item_id, user_id=user_id).first()
    if not item or str(item.user_id) != user_id:
        return jsonify({"error": "Item not found or unauthorized"}), 404
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
    item = StorageItem.query.filter_by(id=item_id, user_id=user_id).first()
    if not item:
        return jsonify({"error": "Fehler beim Löschen des Items"}), 404
    if str(item.user_id) != user_id:
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
    item = StorageItem.query.filter_by(id=item_id, user_id=user_id).first()
    if not item or str(item.user_id) != user_id:
        return jsonify({"error": "Item not found or unauthorized"}), 404

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


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True)
