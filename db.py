import os
import sqlite3
import click
from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def connect_standalone(app):
    """Connection for background threads (outside a request)."""
    conn = sqlite3.connect(app.config["DATABASE"], timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(seed=True):
    db = get_db()
    db.execute("PRAGMA journal_mode = WAL")  # lets web requests and the background email logger run together
    schema = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema, encoding="utf-8") as f:
        db.executescript(f.read())
    if seed:
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            db.execute(
                "INSERT INTO users (username, full_name, email, password_hash, role, must_change_password)"
                " VALUES (?,?,?,?,?,1)",
                ("admin", "System Administrator", "", generate_password_hash("admin123"), "admin"),
            )
        if db.execute("SELECT COUNT(*) FROM departments").fetchone()[0] == 0:
            for name, desc in [
                ("General Medicine", "Outpatient and general consultations"),
                ("Pediatrics", "Child health"),
                ("Obstetrics & Gynaecology", "Maternal and women's health"),
                ("Dentistry", "Dental care"),
            ]:
                db.execute("INSERT INTO departments (name, description) VALUES (?,?)", (name, desc))
    # Give existing doctors a sensible default schedule only when they have
    # no schedule yet: Monday-Friday, 08:00-17:00. Admins can customise it.
    doctors = db.execute("SELECT id FROM doctors").fetchall()
    for doctor in doctors:
        has_schedule = db.execute(
            "SELECT 1 FROM doctor_schedule WHERE doctor_id=? LIMIT 1", (doctor["id"],)
        ).fetchone()
        if not has_schedule:
            db.executemany(
                "INSERT OR IGNORE INTO doctor_schedule (doctor_id, weekday, start_time, end_time, enabled) VALUES (?,?,?,?,1)",
                [(doctor["id"], weekday, "08:00", "17:00") for weekday in range(5)],
            )
    db.commit()


@click.command("init-db")
def init_db_command():
    """Create tables and the default admin (admin / admin123)."""
    os.makedirs(os.path.dirname(current_app.config["DATABASE"]), exist_ok=True)
    init_db()
    click.echo("Database ready. Default login -> admin / admin123 (you must change it on first login).")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
