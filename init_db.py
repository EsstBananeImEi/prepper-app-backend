import os
from app import (
    Category,
    ItemUnit,
    NutrientUnit,
    PackageUnit,
    StorageLocation,
    User,
    db,
    app,
)


def seed_data():
    if not User.query.first():
        user = User(username=os.getenv("ADMIN_USERNAME", "test"))
        user.set_password(os.getenv("ADMIN_PASSWORD", "test"))
        user.set_email(os.getenv("ADMIN_EMAIL", "test"))
        user.activated = True
        user.set_role("admin")

        default_user = User(username=os.getenv("DEFAULT_USERNAME", "default_user"))
        default_user.set_password(os.getenv("DEFAULT_PASSWORD", "default_user"))
        default_user.set_email(os.getenv("DEFAULT_EMAIL", "default_user"))
        user.activated = True
        default_user.set_role("user")

        db.session.add_all([user, default_user])
        db.session.commit()

    default_user = default_user.id

    if not Category.query.first():
        db.session.add_all(
            [
                Category(name="Obst", user_id=default_user),
                Category(name="Gemüse", user_id=default_user),
                Category(name="Fleisch", user_id=default_user),
                Category(name="Milchprodukte", user_id=default_user),
                Category(name="Getreide", user_id=default_user),
                Category(name="Fisch", user_id=default_user),
                Category(name="Backwaren", user_id=default_user),
                Category(name="Wurstwaren", user_id=default_user),
            ]
        )

    if not StorageLocation.query.first():
        db.session.add_all(
            [
                StorageLocation(name="Kühlschrank", user_id=default_user),
                StorageLocation(name="Speisekammer", user_id=default_user),
                StorageLocation(name="Obstkorb", user_id=default_user),
                StorageLocation(name="Kühlregal", user_id=default_user),
            ]
        )

    if not ItemUnit.query.first():
        db.session.add_all(
            [
                ItemUnit(name="Gramm", user_id=default_user),
                ItemUnit(name="Kilogramm", user_id=default_user),
                ItemUnit(name="Liter", user_id=default_user),
                ItemUnit(name="Milliliter", user_id=default_user),
                ItemUnit(name="Stück", user_id=default_user),
            ]
        )

    if not PackageUnit.query.first():
        db.session.add_all(
            [
                PackageUnit(name="Flasche", user_id=default_user),
                PackageUnit(name="Packung", user_id=default_user),
                PackageUnit(name="Dose", user_id=default_user),
                PackageUnit(name="Glas", user_id=default_user),
            ]
        )

    if not NutrientUnit.query.first():
        db.session.add_all(
            [
                NutrientUnit(name="mg", user_id=default_user),
                NutrientUnit(name="g", user_id=default_user),
                NutrientUnit(name="kcal", user_id=default_user),
            ]
        )

        db.session.commit()
        db.session.close()


with app.app_context():
    db.drop_all()
    db.create_all()
    seed_data()
    print("Datenbank erfolgreich initialisiert!")
