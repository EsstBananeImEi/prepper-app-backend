import os
from typing import List, Optional
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flasgger import Swagger
from flask_cors import CORS
import serpapi
import yaml

# Für den neuen 2.0-Stil
from sqlalchemy.orm import Mapped, mapped_column, relationship

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///storage.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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

db = SQLAlchemy(app)


### MODELLDEFINITIONEN im SQLAlchemy 2.0-Stil ###


class StorageItem(db.Model):
    __tablename__ = "storage_item"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(100), nullable=False)
    amount: Mapped[int] = mapped_column(db.Integer, nullable=False)
    categories: Mapped[Optional[str]] = mapped_column(db.String(500))
    lowestAmount: Mapped[int] = mapped_column(db.Integer, nullable=False)
    midAmount: Mapped[int] = mapped_column(db.Integer, nullable=False)
    unit: Mapped[str] = mapped_column(db.String(50), nullable=False)
    packageQuantity: Mapped[Optional[int]] = mapped_column(db.Integer)
    packageUnit: Mapped[Optional[str]] = mapped_column(db.String(50))
    storageLocation: Mapped[str] = mapped_column(db.String(100), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(db.String(200))

    # Eine 1:1-Beziehung zu Nutrient (Cascade-Delete)
    nutrient: Mapped[Optional["Nutrient"]] = relationship(
        "Nutrient",
        uselist=False,
        back_populates="storage_item",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "name", "storageLocation", "unit", name="uq_name_storage_package"
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


class BasketItem(db.Model):
    __tablename__ = "basket_item"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(100), nullable=False)
    amount: Mapped[int] = mapped_column(db.Integer, nullable=True)
    categories: Mapped[Optional[str]] = mapped_column(db.String(500))
    icon: Mapped[Optional[str]] = mapped_column(db.String(200))

    def __init__(self, name: str, amount: int, categories: str, icon: str):
        self.name = name
        self.amount = amount
        self.icon = icon
        self.categories = categories


class Nutrient(db.Model):
    __tablename__ = "nutrient"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    description: Mapped[str] = mapped_column(db.String(200), nullable=False)
    unit: Mapped[str] = mapped_column(db.String(50), nullable=False)
    amount: Mapped[float] = mapped_column(db.Float, nullable=False)
    storage_item_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("storage_item.id"), nullable=False
    )

    # Rückbeziehung zum zugehörigen StorageItem
    storage_item: Mapped["StorageItem"] = relationship(
        "StorageItem", back_populates="nutrient"
    )

    # Eine 1:n-Beziehung zu NutrientValue (Cascade-Delete)
    values: Mapped[List["NutrientValue"]] = relationship(
        "NutrientValue",
        back_populates="nutrient",
        cascade="all, delete-orphan",
    )

    def __init__(
        self, description: str, unit: str, amount: float, storage_item_id: int
    ):
        self.description = description
        self.unit = unit
        self.amount = amount
        self.storage_item_id = storage_item_id


class NutrientValue(db.Model):
    __tablename__ = "nutrient_value"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(100), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(db.String(50))
    nutrient_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("nutrient.id"), nullable=False
    )

    # Rückbeziehung zum zugehörigen Nutrient
    nutrient: Mapped["Nutrient"] = relationship("Nutrient", back_populates="values")

    # 1:n-Beziehung zu NutrientType (Cascade-Delete)
    values: Mapped[List["NutrientType"]] = relationship(
        "NutrientType",
        back_populates="nutrient_value",
        cascade="all, delete-orphan",
    )

    def __init__(self, name: str, color: Optional[str], nutrient_id: int):
        self.name = name
        self.color = color
        self.nutrient_id = nutrient_id


class NutrientType(db.Model):
    __tablename__ = "nutrient_type"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    typ: Mapped[str] = mapped_column(db.String(50), nullable=False)
    value: Mapped[float] = mapped_column(db.Float, nullable=False)
    nutrient_value_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("nutrient_value.id"), nullable=False
    )

    # Rückbeziehung zum zugehörigen NutrientValue
    nutrient_value: Mapped["NutrientValue"] = relationship(
        "NutrientValue", back_populates="values"
    )

    def __init__(self, typ: str, value: float, nutrient_value_id: int):
        self.typ = typ
        self.value = value
        self.nutrient_value_id = nutrient_value_id


class Category(db.Model):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(100), unique=True, nullable=False)

    def __init__(self, name: str):
        self.name = name


class StorageLocation(db.Model):
    __tablename__ = "storage_location"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(100), unique=True, nullable=False)

    def __init__(self, name: str):
        self.name = name


class ItemUnit(db.Model):
    __tablename__ = "item_unit"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(50), unique=True, nullable=False)

    def __init__(self, name: str):
        self.name = name


class PackageUnit(db.Model):
    __tablename__ = "package_unit"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(50), unique=True, nullable=False)

    def __init__(self, name: str):
        self.name = name


class NutrientUnit(db.Model):
    __tablename__ = "nutrient_unit"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(50), unique=True, nullable=False)

    def __init__(self, name: str):
        self.name = name


### ROUTENDEFINITIONEN ###


## BASKET ##
@app.route("/basket", methods=["GET"])
def get_basket():
    items = db.session.query(BasketItem).all()
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
def add_basket_item():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input data"}), 400

    item = db.session.query(BasketItem).filter_by(name=data["name"]).first()
    if item is None:
        item = BasketItem(
            name=data["name"],
            amount=1,
            categories=",".join(data.get("categories", [])),
            icon=data.get("icon"),
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
def update_basket_item(item_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input data"}), 400

    item = db.session.get(BasketItem, item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

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
def delete_basket_item(item_id):
    item = db.session.get(BasketItem, item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

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
def add_bulk_items():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input data"}), 400

    items_to_add = []
    for item_data in data:
        if (
            "name" not in item_data
            or "amount" not in item_data
            or "unit" not in item_data
            or "storageLocation" not in item_data
        ):
            return jsonify({"error": "Invalid input data for one or more items"}), 400

        new_item = StorageItem(
            name=item_data["name"],
            amount=item_data["amount"],
            categories=",".join(item_data.get("categories", [])),
            lowestAmount=item_data["lowestAmount"],
            midAmount=item_data["midAmount"],
            unit=item_data["unit"],
            packageQuantity=item_data.get("packageQuantity"),
            packageUnit=item_data.get("packageUnit"),
            storageLocation=item_data["storageLocation"],
            icon=item_data.get("icon"),
        )
        items_to_add.append(new_item)

    db.session.add_all(items_to_add)
    db.session.flush()  # IDs vergeben

    for item_data in data:
        new_item = StorageItem.query.filter_by(
            name=item_data["name"],
            storageLocation=item_data["storageLocation"],
            unit=item_data["unit"],
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
            )
            db.session.add(nutrient)
            db.session.flush()
            for value_data in nutrient_data.get("values", []):
                nutrient_value = NutrientValue(
                    name=value_data["name"],
                    color=value_data.get("color"),
                    nutrient_id=nutrient.id,
                )
                db.session.add(nutrient_value)
                db.session.flush()
                for type_data in value_data.get("values", []):
                    nutrient_type = NutrientType(
                        typ=type_data["typ"],
                        value=type_data["value"],
                        nutrient_value_id=nutrient_value.id,
                    )
                    db.session.add(nutrient_type)

    db.session.commit()
    return jsonify({"message": "Items added successfully"}), 201


## ITEMS ##
@app.route("/items", methods=["GET"])
def get_items():
    searchstring = request.args.get("q", "")
    query = StorageItem.query

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
def add_item():
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
        name=data["name"], storageLocation=data["storageLocation"], unit=data["unit"]
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
    )

    if not new_item.icon:
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
        )
        db.session.add(nutrient)
        db.session.flush()
        for value_data in nutrient_data.get("values", []):
            nutrient_value = NutrientValue(
                name=value_data["name"],
                color=value_data.get("color"),
                nutrient_id=nutrient.id,
            )
            db.session.add(nutrient_value)
            db.session.flush()
            for type_data in value_data.get("values", []):
                nutrient_type = NutrientType(
                    typ=type_data["typ"],
                    value=type_data["value"],
                    nutrient_value_id=nutrient_value.id,
                )
                db.session.add(nutrient_type)
    db.session.commit()
    return jsonify({"message": "Item added successfully"}), 201


@app.route("/items/<int:item_id>", methods=["PUT"])
def update_item(item_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input data"}), 400

    item = db.session.get(StorageItem, item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

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

    if not item.icon:
        item.icon = get_icon_from_serpapi(item.name)

    db.session.commit()
    return jsonify({"message": "Item updated successfully"}), 200


@app.route("/items/<int:item_id>", methods=["GET"])
def get_item(item_id):
    item = db.session.get(StorageItem, item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

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
def delete_item(item_id):
    item = db.session.get(StorageItem, item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "Item deleted successfully"}), 200


## NUTRIENTS ##
@app.route("/items/<int:item_id>/nutrients", methods=["PUT"])
def update_nutrients(item_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid input data"}), 400

    nutrient_data = data
    item = db.session.get(StorageItem, item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    nutrient = item.nutrient

    if nutrient is None:
        nutrient = Nutrient(
            description=nutrient_data.get("description", ""),
            unit=nutrient_data.get("unit", ""),
            amount=nutrient_data.get("amount", 0.0),
            storage_item_id=item.id,
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
        )
        db.session.add(nv)
        db.session.flush()
        for type_data in value_data.get("values", []):
            nt = NutrientType(
                typ=type_data["typ"],
                value=type_data["value"],
                nutrient_value_id=nv.id,
            )
            db.session.add(nt)

    db.session.commit()
    return jsonify({"message": "Nutrients updated successfully"}), 200


@app.route("/categories", methods=["GET"])
def get_categories():
    categories = Category.query.all()
    return jsonify([{"id": cat.id, "name": cat.name} for cat in categories]), 200


@app.route("/storage-locations", methods=["GET"])
def get_storage_locations():
    locations = StorageLocation.query.all()
    return jsonify([{"id": loc.id, "name": loc.name} for loc in locations]), 200


@app.route("/item-units", methods=["GET"])
def get_item_units():
    units = ItemUnit.query.all()
    return jsonify([{"id": unit.id, "name": unit.name} for unit in units]), 200


@app.route("/package-units", methods=["GET"])
def get_package_units():
    packages = PackageUnit.query.all()
    return (
        jsonify([{"id": package.id, "name": package.name} for package in packages]),
        200,
    )


@app.route("/nutrient-units", methods=["GET"])
def get_nutrient_units():
    nutrients = NutrientUnit.query.all()
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
    search = serpapi.search(params)
    # return the url of the first image
    return search["images_results"][0].get("thumbnail")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True)
