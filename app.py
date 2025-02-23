from functools import lru_cache
import os
import time
from typing import List, Optional, cast
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flasgger import Swagger
from flask_cors import CORS
from requests import HTTPError
import serpapi
import yaml
from sqlalchemy.orm import Mapper
from sqlalchemy import inspect
from werkzeug.security import generate_password_hash, check_password_hash
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
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False  # 15 Minuten
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = 604800  # 7 Tage

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

db = SQLAlchemy(app)


### MODELLDEFINITIONEN im SQLAlchemy 2.0-Stil ###
class User(db.Model):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    username: Mapped[str] = mapped_column(db.String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(db.String(128), nullable=False)
    email: Mapped[str] = mapped_column(db.String(120), unique=False)
    image: Mapped[Optional[str]] = mapped_column(db.String(200))
    admin: Mapped[bool] = mapped_column(db.Boolean, default=False)
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
            "storageLocation",
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
    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "User already exists"}), 409
    user = User(username=data["username"])
    user.set_email(data["email"].lower())
    user.set_password(data["password"])
    user.image = data["image"] or None
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "User created"}), 201


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data or "email" not in data or "password" not in data:
        return jsonify({"error": "Invalid input"}), 400
    user = User.query.filter_by(email=data["email"].lower()).first()
    if not user or not user.check_password(data["password"]):
        return jsonify({"error": "Invalid credentials"}), 401
    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    return (
        jsonify(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email.lower(),
                "image": user.image,
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
    print(current_user)
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
            }
        ),
        200,
    )


@app.route("/user", methods=["PUT"])
@jwt_required()
def update_user():
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input data"}), 400
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    user.username = data.get("username", user.username)
    user.email = data.get("email", user.email).lower()
    if (
        "password" in data
        and data["password"] != ""
        and user.check_password(data["password"])
    ):
        user.set_password(data["password"])
    else:
        return jsonify({"error": "Invalid password"}), 400
    user.image = data.get("image", user.image) or None

    db.session.commit()
    return jsonify({"message": "User updated successfully"}), 200


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
    print(user_id)
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
    if not item or str(item.user_id) != user_id:
        return jsonify({"error": "Item not found or unauthorized"}), 404

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
        or "storageLocation" not in data
        or data["name"] == ""
        or data["amount"] == ""
        or data["unit"] == ""
        or data["storageLocation"] == ""
    ):
        return jsonify({"error": "Invalid input data"}), 400

    duplicate_item = StorageItem.query.filter_by(
        name=data["name"],
        storageLocation=data["storageLocation"],
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
    return jsonify({"message": "Item added successfully"}), 201


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

    if not item.icon or item.icon == "":
        item.icon = get_icon_from_serpapi(item.name)

    db.session.commit()
    return jsonify({"message": "Item updated successfully"}), 200


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
    item = db.session.get(StorageItem, {"id": item_id, "user_id": user_id})
    if not item or item.user_id != user_id:
        return jsonify({"error": "Item not found or unauthorized"}), 404

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
    item = db.session.get(StorageItem, {"id": item_id, "user_id": user_id})
    if not item or item.user_id != user_id:
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
    return jsonify({"message": "Nutrients updated successfully"}), 200


@app.route("/categories", methods=["GET"])
@jwt_required()
def get_categories():
    user_id = get_jwt_identity()
    categories = db.session.query(Category).filter_by(user_id=user_id).all()
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
