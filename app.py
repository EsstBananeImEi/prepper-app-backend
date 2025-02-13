from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flasgger import Swagger
from flask_cors import CORS  # Importiere CORS
import yaml

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///storage.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Aktivieren von CORS für alle Routen
CORS(app)
# Aktivieren von CORS nur für einen bestimmten Ursprung
CORS(app, origins=["http://localhost:3000"])
# Swagger initialisieren
with open("swagger.yaml", "r") as f:
    swagger_template = yaml.safe_load(f)

swagger = Swagger(app, template=swagger_template)

db = SQLAlchemy(app)


class StorageItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    amount = db.Column(db.Integer, nullable=False)
    categories = db.Column(db.String(500))
    lowestAmount = db.Column(db.Integer, nullable=False)
    midAmount = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(50), nullable=False)
    packageQuantity = db.Column(db.Integer)
    packageUnit = db.Column(db.String(50))
    storageLocation = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(200))
    # Cascade-Delete: Das einzelne Nutrient-Objekt wird mit gelöscht.
    nutrient = db.relationship(
        "Nutrient",
        uselist=False,
        backref="storage_item",
        lazy=True,
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
        packageQuantity: int | None = None,
        packageUnit: str | None = None,
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


class Nutrient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    unit = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    storage_item_id = db.Column(
        db.Integer, db.ForeignKey("storage_item.id"), nullable=False
    )
    # Cascade-Delete für NutrientValue-Einträge
    values = db.relationship(
        "NutrientValue", backref="nutrient", lazy=True, cascade="all, delete-orphan"
    )

    def __init__(
        self, description: str, unit: str, amount: float, storage_item_id: int
    ):
        self.description = description
        self.unit = unit
        self.amount = amount
        self.storage_item_id = storage_item_id


class NutrientValue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(50))
    nutrient_id = db.Column(db.Integer, db.ForeignKey("nutrient.id"), nullable=False)
    # Cascade-Delete für NutrientType-Einträge
    values = db.relationship(
        "NutrientType",
        backref="nutrient_value",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def __init__(self, name: str, color: str | None, nutrient_id: int):
        self.name = name
        self.color = color
        self.nutrient_id = nutrient_id


class NutrientType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    typ = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Float, nullable=False)
    nutrient_value_id = db.Column(
        db.Integer, db.ForeignKey("nutrient_value.id"), nullable=False
    )

    def __init__(self, typ: str, value: float, nutrient_value_id: int):
        self.typ = typ
        self.value = value
        self.nutrient_value_id = nutrient_value_id


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def __init__(self, name: str):
        self.name = name


class StorageLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def __init__(self, name: str):
        self.name = name


class ItemUnit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    def __init__(self, name: str):
        self.name = name


class PackageUnit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    def __init__(self, name: str):
        self.name = name


class NutrientUnit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    def __init__(self, name: str):
        self.name = name


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

        # Neues StorageItem erstellen
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

    # Optional: Falls Nutrient-Daten in der Anfrage enthalten sind, hinzufügen.
    # Hier wird davon ausgegangen, dass nutrient als einzelnes Objekt in der Anfrage übergeben wird.
    for item_data in data:
        new_item = StorageItem.query.filter_by(
            name=item_data["name"], unit=item_data["unit"]
        ).first()
        if "nutrients" in item_data and item_data["nutrients"]:
            nutrient_data = item_data["nutrients"]  # nutrient als Objekt
            nutrient = Nutrient(
                description=nutrient_data["description"],
                unit=nutrient_data["unit"],
                amount=nutrient_data["amount"],
                storage_item_id=new_item.id,  # type: ignore
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
    ):
        return jsonify({"error": "Invalid input data"}), 400

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
    db.session.add(new_item)
    db.session.flush()  # new_item.id verfügbar

    if "nutrients" in data and data["nutrients"]:
        nutrient_data = data["nutrients"]  # nutrient als einzelnes Objekt
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

    item = StorageItem.query.get(item_id)
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

    db.session.commit()
    return jsonify({"message": "Item updated successfully"}), 200


@app.route("/items/<int:item_id>", methods=["GET"])
def get_item(item_id):
    item = StorageItem.query.get(item_id)
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


@app.route("/items/<int:item_id>/nutrients", methods=["PUT"])
def update_nutrients(item_id):
    data = request.get_json()
    if not data or "nutrients" not in data:
        return jsonify({"error": "No nutrients data provided"}), 400

    item = StorageItem.query.get(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    # Lösche das bestehende Nutrient-Objekt (und dessen untergeordnete Einträge)
    if item.nutrient:
        db.session.delete(item.nutrient)
        db.session.flush()

    # Füge das neue Nutrient-Objekt hinzu
    nutrient_data = data["nutrients"]
    nutrient = Nutrient(
        description=nutrient_data["description"],
        unit=nutrient_data["unit"],
        amount=nutrient_data["amount"],
        storage_item_id=item.id,
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


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
