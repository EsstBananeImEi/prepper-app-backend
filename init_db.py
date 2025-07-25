import os
from app import (
    Category,
    ItemUnit,
    NutrientUnit,
    PackageUnit,
    StorageLocation,
    User,
    Group,
    UserGroup,
    GroupInvitation,
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
        user.groups = []

        default_user = User(username=os.getenv("DEFAULT_USERNAME", "default_user"))
        default_user.set_password(os.getenv("DEFAULT_PASSWORD", "default_user"))
        default_user.set_email(os.getenv("DEFAULT_EMAIL", "default_user"))
        default_user.activated = True
        default_user.set_role("user")
        default_user.groups = []

        db.session.add_all([user, default_user])
        db.session.commit()

    # Benutzer für weitere Referenzen abrufen
    admin_user = User.query.filter_by(
        username=os.getenv("ADMIN_USERNAME", "test")
    ).first()
    default_user_obj = User.query.filter_by(
        username=os.getenv("DEFAULT_USERNAME", "default_user")
    ).first()
    default_user_id = default_user_obj.id if default_user_obj else 1

    if not Category.query.first():
        db.session.add_all(
            [
                Category(name="Obst", user_id=default_user_id),
                Category(name="Gemüse", user_id=default_user_id),
                Category(name="Fleisch", user_id=default_user_id),
                Category(name="Milchprodukte", user_id=default_user_id),
                Category(name="Getreide", user_id=default_user_id),
                Category(name="Fisch", user_id=default_user_id),
                Category(name="Backwaren", user_id=default_user_id),
                Category(name="Wurstwaren", user_id=default_user_id),
            ]
        )

    if not StorageLocation.query.first():
        db.session.add_all(
            [
                StorageLocation(name="Kühlschrank", user_id=default_user_id),
                StorageLocation(name="Speisekammer", user_id=default_user_id),
                StorageLocation(name="Obstkorb", user_id=default_user_id),
                StorageLocation(name="Kühlregal", user_id=default_user_id),
            ]
        )

    if not ItemUnit.query.first():
        db.session.add_all(
            [
                ItemUnit(name="Gramm", user_id=default_user_id),
                ItemUnit(name="Kilogramm", user_id=default_user_id),
                ItemUnit(name="Liter", user_id=default_user_id),
                ItemUnit(name="Milliliter", user_id=default_user_id),
                ItemUnit(name="Stück", user_id=default_user_id),
            ]
        )

    if not PackageUnit.query.first():
        db.session.add_all(
            [
                PackageUnit(name="Flasche", user_id=default_user_id),
                PackageUnit(name="Packung", user_id=default_user_id),
                PackageUnit(name="Dose", user_id=default_user_id),
                PackageUnit(name="Glas", user_id=default_user_id),
            ]
        )

    if not NutrientUnit.query.first():
        db.session.add_all(
            [
                NutrientUnit(name="mg", user_id=default_user_id),
                NutrientUnit(name="g", user_id=default_user_id),
                NutrientUnit(name="kcal", user_id=default_user_id),
            ]
        )

        # Beispielgruppen erstellen
        # if not Group.query.first() and admin_user and default_user_obj:
        #     # Eine Beispielgruppe erstellen
        #     example_group = Group(
        #         name="Familie Schmidt",
        #         description="Gemeinsame Vorräte für die Familie",
        #         created_by=admin_user.id,
        #     )
        #     db.session.add(example_group)
        #     db.session.commit()

        #     # Den Admin und den Default-User zur Gruppe hinzufügen
        #     admin_membership = UserGroup(
        #         user_id=admin_user.id, group_id=example_group.id, role="admin"
        #     )
        #     default_membership = UserGroup(
        #         user_id=default_user_obj.id, group_id=example_group.id, role="member"
        #     )
        #     db.session.add_all([admin_membership, default_membership])

        db.session.commit()
        db.session.close()


with app.app_context():
    db.drop_all()
    db.create_all()
    seed_data()
    print("Datenbank erfolgreich initialisiert!")
