"""Staff accounts (administrators and receptionists). Doctors are managed in doctors.py."""
import re
import secrets
import sqlite3
from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for, abort
from werkzeug.security import generate_password_hash
from db import get_db
from security import roles_required
import mailer

bp = Blueprint("users", __name__, url_prefix="/users")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def temp_password():
    return secrets.token_urlsafe(9)


@bp.route("/")
@roles_required("admin")
def index():
    rows = get_db().execute("SELECT * FROM users WHERE role <> 'doctor' ORDER BY role, full_name").fetchall()
    return render_template("users/list.html", rows=rows)


@bp.route("/new", methods=["GET", "POST"])
@roles_required("admin")
def create():
    u = {"full_name": "", "username": "", "email": "", "role": "receptionist"}
    if request.method == "POST":
        u = {k: request.form.get(k, "").strip() for k in ("full_name", "username", "email", "role")}
        pw = request.form.get("password", "").strip() or temp_password()
        errs = []
        if not u["full_name"] or not u["username"]:
            errs.append("Full name and username are required.")
        if u["role"] not in ("admin", "receptionist"):
            errs.append("Invalid role.")
        if u["email"] and not EMAIL_RE.match(u["email"]):
            errs.append("Email looks invalid.")
        if len(pw) < 8:
            errs.append("Password must be at least 8 characters.")
        if errs:
            for e in errs:
                flash(e, "danger")
        else:
            try:
                db = get_db()
                db.execute("INSERT INTO users (username, full_name, email, password_hash, role, must_change_password)"
                           " VALUES (?,?,?,?,?,1)",
                           (u["username"], u["full_name"], u["email"] or None, generate_password_hash(pw), u["role"]))
                db.commit()
                mailer.welcome_user(current_app._get_current_object(), u, u["username"], pw)
                msg = f"Account created. Temporary password: {pw}"
                if u["email"]:
                    msg += " (also emailed to the user)"
                flash(msg, "success")
                return redirect(url_for("users.index"))
            except sqlite3.IntegrityError:
                flash("That username is already taken.", "danger")
    return render_template("users/form.html", u=u)


@bp.route("/<int:uid>/toggle", methods=["POST"])
@roles_required("admin")
def toggle(uid):
    if uid == g.user["id"]:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("users.index"))
    db = get_db()
    db.execute("UPDATE users SET is_active = 1 - is_active WHERE id=?", (uid,))
    db.commit()
    flash("Account status changed.", "info")
    return redirect(request.referrer or url_for("users.index"))


@bp.route("/<int:uid>/reset-password", methods=["POST"])
@roles_required("admin")
def reset_password(uid):
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        abort(404)
    pw = temp_password()
    db.execute("UPDATE users SET password_hash=?, must_change_password=1 WHERE id=?", (generate_password_hash(pw), uid))
    db.commit()
    mailer.welcome_user(current_app._get_current_object(), u, u["username"], pw)
    flash(f"New temporary password for {u['username']}: {pw}" + (" (also emailed)" if u["email"] else ""), "success")
    return redirect(request.referrer or url_for("users.index"))
