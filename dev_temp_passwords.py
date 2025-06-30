#!/usr/bin/env python3
"""
ENTWICKLUNGS-TOOL: Temporäre Klartext-Passwörter
WARNUNG: NUR FÜR ENTWICKLUNG VERWENDEN!

Dieses Script erstellt eine Tabelle für temporäre Klartext-Passwörter,
die nur für Entwicklungszwecke verwendet werden sollte.
"""

import os
from app import app, db
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime


# Erstelle eine temporäre Tabelle für Entwicklung
class TempPassword(db.Model):
    __tablename__ = "temp_passwords"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    username = Column(String(80), nullable=False)
    temp_password = Column(
        String(200), nullable=False
    )  # KLARTEXT - NUR FÜR ENTWICKLUNG!
    created_at = Column(DateTime, default=datetime.utcnow)
    note = Column(String(500))


def create_temp_password_table():
    """Erstelle die temporäre Passwort-Tabelle"""
    with app.app_context():
        db.create_all()
        print("✓ Temporäre Passwort-Tabelle erstellt.")


def add_temp_password(user_id, username, password, note=""):
    """Füge ein temporäres Passwort hinzu"""
    with app.app_context():
        temp_pass = TempPassword(
            user_id=user_id, username=username, temp_password=password, note=note
        )
        db.session.add(temp_pass)
        db.session.commit()
        print(f"✓ Temporäres Passwort für {username} gespeichert.")


def list_temp_passwords():
    """Zeige alle temporären Passwörter"""
    with app.app_context():
        temp_passwords = TempPassword.query.all()

        if not temp_passwords:
            print("Keine temporären Passwörter gefunden.")
            return

        print("\n=== TEMPORÄRE PASSWÖRTER (NUR ENTWICKLUNG!) ===")
        print(f"{'ID':<5} {'Username':<20} {'Passwort':<20} {'Erstellt':<20} {'Notiz'}")
        print("-" * 90)

        for temp in temp_passwords:
            created = temp.created_at.strftime("%Y-%m-%d %H:%M")
            note = temp.note or ""
            print(
                f"{temp.user_id:<5} {temp.username:<20} {temp.temp_password:<20} {created:<20} {note}"
            )


def clear_temp_passwords():
    """Lösche alle temporären Passwörter"""
    with app.app_context():
        count = TempPassword.query.count()
        if count == 0:
            print("Keine temporären Passwörter zum Löschen.")
            return

        confirm = input(f"Wirklich {count} temporäre Passwörter löschen? (j/N): ")
        if confirm.lower() in ["j", "ja", "y", "yes"]:
            TempPassword.query.delete()
            db.session.commit()
            print(f"✓ {count} temporäre Passwörter gelöscht.")
        else:
            print("Abgebrochen.")


def main():
    print("=== ENTWICKLUNGS-TOOL: Temporäre Passwörter ===")
    print("⚠️  WARNUNG: Dieses Tool speichert Passwörter im Klartext!")
    print("⚠️  NUR FÜR ENTWICKLUNG VERWENDEN!")
    print()

    while True:
        print("\nOptionen:")
        print("1. Tabelle erstellen")
        print("2. Temporäres Passwort hinzufügen")
        print("3. Alle temporären Passwörter anzeigen")
        print("4. Alle temporären Passwörter löschen")
        print("5. Beenden")

        choice = input("\nWähle eine Option (1-5): ").strip()

        if choice == "1":
            create_temp_password_table()
        elif choice == "2":
            user_id = int(input("User ID: "))
            username = input("Username: ")
            password = input("Temporäres Passwort: ")
            note = input("Notiz (optional): ")
            add_temp_password(user_id, username, password, note)
        elif choice == "3":
            list_temp_passwords()
        elif choice == "4":
            clear_temp_passwords()
        elif choice == "5":
            print("Auf Wiedersehen!")
            break
        else:
            print("Ungültige Option.")


if __name__ == "__main__":
    main()
