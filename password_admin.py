#!/usr/bin/env python3
"""
Admin-Tool zum Zurücksetzen von Passwörtern
Da Hash-Funktionen Einwegfunktionen sind, können Passwörter nicht "enthasht" werden.
Dieses Script erlaubt es dir, neue Passwörter für Benutzer zu setzen.
"""

import os
import sys
from getpass import getpass
from werkzeug.security import generate_password_hash

# Importiere die App und Models
try:
    from app import app, db, User
except ImportError:
    print(
        "Fehler: Kann app.py nicht importieren. Stelle sicher, dass du im richtigen Verzeichnis bist."
    )
    sys.exit(1)


def list_users():
    """Zeige alle Benutzer an"""
    with app.app_context():
        users = User.query.all()
        if not users:
            print("Keine Benutzer gefunden.")
            return

        print("\n=== Alle Benutzer ===")
        print(f"{'ID':<5} {'Username':<20} {'Email':<30} {'Admin':<10} {'Activated'}")
        print("-" * 80)
        for user in users:
            activated = "✓" if user.activated else "✗"
            admin_status = "✓" if user.admin else "✗"
            print(
                f"{user.id:<5} {user.username:<20} {user.email:<30} {admin_status:<10} {activated}"
            )


def reset_user_password():
    """Setze ein neues Passwort für einen Benutzer"""
    with app.app_context():
        # Zeige alle Benutzer
        list_users()

        # Benutzer auswählen
        try:
            user_input = input("\nGib die Benutzer-ID oder den Username ein: ").strip()

            # Versuche erst ID, dann Username
            user = None
            if user_input.isdigit():
                user = User.query.get(int(user_input))

            if not user:
                user = User.query.filter_by(username=user_input).first()

            if not user:
                print(f"Benutzer '{user_input}' nicht gefunden.")
                return

        except ValueError:
            print("Ungültige Eingabe.")
            return

        print(f"\nBenutzer gefunden: {user.username} ({user.email})")

        # Neues Passwort eingeben
        while True:
            new_password = getpass("Neues Passwort eingeben: ")
            if len(new_password) < 6:
                print("Passwort muss mindestens 6 Zeichen lang sein.")
                continue

            confirm_password = getpass("Passwort bestätigen: ")
            if new_password != confirm_password:
                print("Passwörter stimmen nicht überein.")
                continue

            break

        # Passwort setzen
        user.set_password(new_password)
        db.session.commit()

        print(f"✓ Passwort für Benutzer '{user.username}' erfolgreich zurückgesetzt!")


def create_admin_user():
    """Erstelle einen neuen Admin-Benutzer"""
    with app.app_context():
        username = input("Admin Username: ").strip()

        # Prüfe ob Username bereits existiert
        if User.query.filter_by(username=username).first():
            print(f"Benutzer '{username}' existiert bereits.")
            return

        email = input("Admin Email: ").strip()

        # Prüfe ob Email bereits existiert
        if User.query.filter_by(email=email).first():
            print(f"Email '{email}' wird bereits verwendet.")
            return

        # Passwort eingeben
        while True:
            password = getpass("Admin Passwort: ")
            if len(password) < 6:
                print("Passwort muss mindestens 6 Zeichen lang sein.")
                continue

            confirm_password = getpass("Passwort bestätigen: ")
            if password != confirm_password:
                print("Passwörter stimmen nicht überein.")
                continue

            break

        # Admin erstellen
        admin = User(username=username)
        admin.set_password(password)
        admin.set_email(email)
        admin.activated = True
        admin.set_role("admin")

        db.session.add(admin)
        db.session.commit()

        print(f"✓ Admin-Benutzer '{username}' erfolgreich erstellt!")


def show_password_hash(username_or_id):
    """Zeige den aktuellen Password-Hash eines Benutzers (für Debug-Zwecke)"""
    with app.app_context():
        user = None
        if username_or_id.isdigit():
            user = User.query.get(int(username_or_id))
        else:
            user = User.query.filter_by(username=username_or_id).first()

        if not user:
            print(f"Benutzer '{username_or_id}' nicht gefunden.")
            return

        print(f"\nBenutzer: {user.username}")
        print(f"Hash: {user.password_hash}")
        print("\nHinweis: Dieser Hash kann NICHT rückgängig gemacht werden!")


def show_temp_passwords():
    """Zeige temporäre Klartext-Passwörter (nur für Entwicklung!)"""
    try:
        # Versuche temporäre Passwort-Tabelle zu importieren
        with app.app_context():
            # Prüfe ob die Tabelle existiert
            from sqlalchemy import inspect

            inspector = inspect(db.engine)
            if "temp_passwords" not in inspector.get_table_names():
                print("⚠️  Keine temporären Passwörter gefunden.")
                print(
                    "Hinweis: Verwende 'Temporäres Passwort speichern' um Passwörter zu verfolgen."
                )
                return

            # Importiere das temporäre Model
            from dev_temp_passwords import TempPassword

            temp_passwords = TempPassword.query.all()

            if not temp_passwords:
                print("Keine temporären Passwörter gespeichert.")
                return

            print("\n=== TEMPORÄRE PASSWÖRTER (NUR ENTWICKLUNG!) ===")
            print("⚠️  WARNUNG: Diese Passwörter sind im Klartext gespeichert!")
            print(
                f"{'User ID':<8} {'Username':<20} {'Temp Passwort':<20} {'Erstellt':<20}"
            )
            print("-" * 80)

            for temp in temp_passwords:
                created = temp.created_at.strftime("%Y-%m-%d %H:%M")
                print(
                    f"{temp.user_id:<8} {temp.username:<20} {temp.temp_password:<20} {created:<20}"
                )

    except ImportError:
        print("⚠️  Entwicklungs-Tool nicht verfügbar.")
        print(
            "Führe 'python dev_temp_passwords.py' aus, um temporäre Passwörter zu verwalten."
        )


def save_temp_password():
    """Speichere ein temporäres Klartext-Passwort (nur für Entwicklung!)"""
    with app.app_context():
        try:
            # Importiere und erstelle Tabelle falls nötig
            from dev_temp_passwords import TempPassword

            db.create_all()

            # Zeige Benutzer
            list_users()

            # Benutzer auswählen
            user_input = input("\nGib die Benutzer-ID oder den Username ein: ").strip()

            user = None
            if user_input.isdigit():
                user = User.query.get(int(user_input))

            if not user:
                user = User.query.filter_by(username=user_input).first()

            if not user:
                print(f"Benutzer '{user_input}' nicht gefunden.")
                return

            # Temporäres Passwort eingeben
            temp_password = input(f"Temporäres Passwort für {user.username}: ").strip()
            note = input("Notiz (optional): ").strip()

            # Prüfe ob bereits ein Eintrag existiert
            existing = TempPassword.query.filter_by(user_id=user.id).first()
            if existing:
                existing.temp_password = temp_password
                existing.note = note
                existing.created_at = db.func.now()

            db.session.commit()
            print(f"✓ Temporäres Passwort für '{user.username}' gespeichert!")
            print(
                "⚠️  WARNUNG: Passwort ist im Klartext gespeichert - nur für Entwicklung!"
            )

        except ImportError:
            print("⚠️  Entwicklungs-Tool nicht verfügbar.")
            print(
                "Führe 'python dev_temp_passwords.py' aus, um die Tabelle zu erstellen."
            )


def main():
    print("=== Prepper App - Password Admin Tool ===")
    print(
        "Hinweis: Passwörter können nicht 'enthasht' werden - das ist ein Sicherheitsfeature!"
    )
    print()

    while True:
        print("\nOptionen:")
        print("1. Alle Benutzer anzeigen")
        print("2. Passwort zurücksetzen")
        print("3. Admin-Benutzer erstellen")
        print("4. Password-Hash anzeigen (Debug)")
        print("5. Temporäre Passwörter anzeigen (Entwicklung)")
        print("6. Temporäres Passwort speichern (Entwicklung)")
        print("7. Beenden")

        choice = input("\nWähle eine Option (1-7): ").strip()

        if choice == "1":
            list_users()
        elif choice == "2":
            reset_user_password()
        elif choice == "3":
            create_admin_user()
        elif choice == "4":
            user_input = input("Username oder ID: ").strip()
            show_password_hash(user_input)
        elif choice == "5":
            show_temp_passwords()
        elif choice == "6":
            save_temp_password()
        elif choice == "7":
            print("Auf Wiedersehen!")
            break
        else:
            print("Ungültige Option.")


if __name__ == "__main__":
    main()
