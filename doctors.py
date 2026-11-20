import re
import sqlite3
from datetime import datetime
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for, abort
from werkzeug.security import generate_password_hash
from db import get_db
from security import roles_required, login_required
from blueprints.users import temp_password
import mailer

bp = Blueprint("doctors", __name__, url_prefix="/doctors")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
WEEKDAYS = [(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"),
            (4, "Friday"), (5, "Saturday"), (6, "Sunday")]


def _default_schedule():
    return {day: {"enabled": day < 5, "start_time": "08:00", "end_time": "17:00"}
            for day, _ in WEEKDAYS}


def _read_schedule_form():
    schedule = {}
    errors = []
    for day, label in WEEKDAYS:
        enabled = request.form.get(f"schedule_{day}_enabled") == "on"
        start = request.form.get(f"schedule_{day}_start", "08:00").strip()
        end = request.form.get(f"schedule_{day}_end", "17:00").strip()
        if enabled:
            try:
                start_dt = datetime.strptime(start, "%H:%M")
                end_dt = datetime.strptime(end, "%H:%M")
                if start_dt >= end_dt:
                    raise ValueError
            except ValueError:
                errors.append(f"Enter valid start and end times for {label}; end must be later than start.")
        schedule[day] = {"enabled": enabled, "start_time": start, "end_time": end}
    if not any(v["enabled"] for v in schedule.values()):
        errors.append("Enable at least one working day for this doctor.")
    return schedule, errors


def _save_schedule(db, doctor_id, schedule):
    db.execute("DELETE FROM doctor_schedule WHERE doctor_id=?", (doctor_id,))
    db.executemany(
        "INSERT INTO doctor_schedule (doctor_id, weekday, start_time, end_time, enabled) VALUES (?,?,?,?,?)",
        [(doctor_id, day, values["start_time"], values["end_time"], int(values["enabled"]))
         for day, values in schedule.items()],
    )


def _load_schedule(db, doctor_id):
    schedule = _default_schedule()
    rows = db.execute("SELECT weekday, start_time, end_time, enabled FROM doctor_schedule WHERE doctor_id=?",
                      (doctor_id,)).fetchall()
    if rows:
        schedule = {day: {"enabled": False, "start_time": "08:00", "end_time": "17:00"}
                    for day, _ in WEEKDAYS}
        for row in rows:
            schedule[row["weekday"]] = {"enabled": bool(row["enabled"]),
                                         "start_time": row["start_time"], "end_time": row["end_time"]}
    return schedule

BASE_Q = ("SELECT d.*, u.full_name, u.username, u.email, u.is_active, dep.name AS department "
          "FROM doctors d JOIN users u ON u.id=d.user_id LEFT JOIN departments dep ON dep.id=d.department_id ")


def _departments():
    return get_db().execute("SELECT * FROM departments ORDER BY name").fetchall()


def _dept_options():
    return [(x["id"], x["name"]) for x in _departments()]


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    dep = request.args.get("department", "")
    where, args = [], []
    if q:
        where.append("(u.full_name LIKE ? OR d.specialization LIKE ?)"); args += [f"%{q}%"] * 2
    if dep:
        where.append("d.department_id = ?"); args.append(dep)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = get_db().execute(BASE_Q + clause + " ORDER BY u.full_name", args).fetchall()
    return render_template("doctors/list.html", rows=rows, q=q, dep=dep, departments=_departments())


@bp.route("/new", methods=["GET", "POST"])
@roles_required("admin")
def create():
    d = {"full_name": "", "username": "", "email": "", "department_id": "", "specialization": "", "phone": "", "license_no": ""}
    schedule = _default_schedule()
    if request.method == "POST":
        d = {k: request.form.get(k, "").strip() for k in d}
        schedule, schedule_errors = _read_schedule_form()
        pw = request.form.get("password", "").strip() or temp_password()
        errs = list(schedule_errors)
        if not d["full_name"] or not d["username"]:
            errs.append("Full name and username are required.")
        if d["email"] and not EMAIL_RE.match(d["email"]):
            errs.append("Email looks invalid.")
        if len(pw) < 8:
            errs.append("Password must be at least 8 characters.")
        if errs:
            for e in errs:
                flash(e, "danger")
        else:
            db = get_db()
            try:
                cur = db.execute("INSERT INTO users (username, full_name, email, password_hash, role, must_change_password)"
                                 " VALUES (?,?,?,?, 'doctor', 1)",
                                 (d["username"], d["full_name"], d["email"] or None, generate_password_hash(pw)))
                doctor_cur = db.execute("INSERT INTO doctors (user_id, department_id, specialization, phone, license_no) VALUES (?,?,?,?,?)",
                           (cur.lastrowid, d["department_id"] or None, d["specialization"], d["phone"], d["license_no"]))
                _save_schedule(db, doctor_cur.lastrowid, schedule)
                db.commit()
                mailer.welcome_user(current_app._get_current_object(), d, d["username"], pw)
                flash(f"Doctor registered. Temporary password: {pw}" + (" (also emailed)" if d["email"] else ""), "success")
                return redirect(url_for("doctors.index"))
            except sqlite3.IntegrityError:
                db.rollback()
                flash("That username is already taken.", "danger")
    return render_template("doctors/form.html", d=d, dept_options=_dept_options(), editing=False,
                           schedule=schedule, weekdays=WEEKDAYS)


@bp.route("/<int:did>/edit", methods=["GET", "POST"])
@roles_required("admin")
def edit(did):
    db = get_db()
    d = db.execute(BASE_Q + "WHERE d.id=?", (did,)).fetchone()
    if not d:
        abort(404)
    schedule = _load_schedule(db, did)
    if request.method == "POST":
        f = {k: request.form.get(k, "").strip() for k in ("full_name", "email", "department_id", "specialization", "phone", "license_no")}
        schedule, schedule_errors = _read_schedule_form()
        errors = list(schedule_errors)
        if not f["full_name"]:
            errors.append("Full name is required.")
        if f["email"] and not EMAIL_RE.match(f["email"]):
            errors.append("Email looks invalid.")
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            db.execute("UPDATE users SET full_name=?, email=? WHERE id=?", (f["full_name"], f["email"] or None, d["user_id"]))
            db.execute("UPDATE doctors SET department_id=?, specialization=?, phone=?, license_no=? WHERE id=?",
                       (f["department_id"] or None, f["specialization"], f["phone"], f["license_no"], did))
            _save_schedule(db, did, schedule)
            db.commit()
            flash("Doctor and weekly availability updated.", "success")
            return redirect(url_for("doctors.index"))
        d = dict(d, **f)
    return render_template("doctors/form.html", d=d, dept_options=_dept_options(), editing=True,
                           schedule=schedule, weekdays=WEEKDAYS)
