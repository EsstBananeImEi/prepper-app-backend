from app import Category, ItemUnit, NutrientUnit, PackageUnit, StorageLocation, db, app


def seed_data():
    if not Category.query.first():
        db.session.add_all(
            [
                Category(name="Obst"),
                Category(name="Gemüse"),
                Category(name="Fleisch"),
                Category(name="Milchprodukte"),
                Category(name="Getreide"),
                Category(name="Fisch"),
                Category(name="Backwaren"),
                Category(name="Wurstwaren"),
            ]
        )

    if not StorageLocation.query.first():
        db.session.add_all(
            [
                StorageLocation(name="Kühlschrank"),
                StorageLocation(name="Speisekammer"),
                StorageLocation(name="Obstkorb"),
                StorageLocation(name="Kühlregal"),
            ]
        )

    if not ItemUnit.query.first():
        db.session.add_all(
            [
                ItemUnit(name="Gramm"),
                ItemUnit(name="Kilogramm"),
                ItemUnit(name="Liter"),
                ItemUnit(name="Milliliter"),
                ItemUnit(name="Stück"),
            ]
        )

    if not PackageUnit.query.first():
        db.session.add_all(
            [
                PackageUnit(name="Flasche"),
                PackageUnit(name="Packung"),
                PackageUnit(name="Dose"),
                PackageUnit(name="Glas"),
            ]
        )

    if not NutrientUnit.query.first():
        db.session.add_all(
            [
                NutrientUnit(name="mg"),
                NutrientUnit(name="g"),
                NutrientUnit(name="kcal"),
            ]
        )

        db.session.commit()
        db.session.close()


with app.app_context():
    db.drop_all()
    db.create_all()
    seed_data()
    print("Datenbank erfolgreich initialisiert!")
