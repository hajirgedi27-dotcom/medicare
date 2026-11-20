import re
import sqlite3
from flask import Blueprint, flash, g, redirect, render_template, request, url_for, abort
from db import get_db
from security import login_required, roles_required

bp = Blueprint("patients", __name__, url_prefix="/patients")
PER_PAGE = 15
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BLOOD = [(b, b) for b in ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")]


def _form():
    f = request.form
    return {k: f.get(k, "").strip() for k in (
        "full_name", "gender", "date_of_birth", "phone", "email", "address", "national_id",
        "blood_group", "allergies", "next_of_kin", "next_of_kin_phone")}


def _validate(d):
    errors = []
    if not d["full_name"]:
        errors.append("Full name is required.")
    if d["gender"] not in ("Male", "Female", "Other"):
        errors.append("Please select a gender.")
    if d["email"] and not EMAIL_RE.match(d["email"]):
        errors.append("Email address looks invalid.")
    if not d["phone"]:
        errors.append("Phone number is required.")
    return errors


@bp.route("/")
@login_required
def index():
    db = get_db()
    q = request.args.get("q", "").strip()
    gender = request.args.get("gender", "")
    blood = request.args.get("blood_group", "")
    page = max(int(request.args.get("page", 1) or 1), 1)
    where, args = [], []
    if q:
        where.append("(full_name LIKE ? OR phone LIKE ? OR patient_no LIKE ? OR national_id LIKE ? OR email LIKE ?)")
        args += [f"%{q}%"] * 5
    if gender:
        where.append("gender = ?"); args.append(gender)
    if blood:
        where.append("blood_group = ?"); args.append(blood)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = db.execute(f"SELECT COUNT(*) FROM patients {clause}", args).fetchone()[0]
    rows = db.execute(f"SELECT * FROM patients {clause} ORDER BY id DESC LIMIT ? OFFSET ?",
                      args + [PER_PAGE, (page - 1) * PER_PAGE]).fetchall()
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    return render_template("patients/list.html", rows=rows, q=q, gender=gender, blood=blood,
                           page=page, pages=pages, total=total)


@bp.route("/new", methods=["GET", "POST"])
@roles_required("admin", "receptionist")
def create():
    data = {k: "" for k in ("full_name", "gender", "date_of_birth", "phone", "email", "address", "national_id",
                            "blood_group", "allergies", "next_of_kin", "next_of_kin_phone")}
    if request.method == "POST":
        data = _form()
        errors = _validate(data)
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            db = get_db()
            nxt = (db.execute("SELECT COALESCE(MAX(id),0)+1 FROM patients").fetchone()[0])
            cur = db.execute(
                "INSERT INTO patients (patient_no, full_name, gender, date_of_birth, phone, email, address, national_id,"
                " blood_group, allergies, next_of_kin, next_of_kin_phone) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"P-{nxt:06d}", data["full_name"], data["gender"], data["date_of_birth"] or None, data["phone"],
                 data["email"] or None, data["address"], data["national_id"] or None, data["blood_group"] or None,
                 data["allergies"], data["next_of_kin"], data["next_of_kin_phone"]))
            db.commit()
            flash("Patient registered.", "success")
            return redirect(url_for("patients.view", pid=cur.lastrowid))
    return render_template("patients/form.html", p=data, editing=False, blood_options=BLOOD)


@bp.route("/<int:pid>")
@login_required
def view(pid):
    db = get_db()
    p = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    appts = db.execute(
        "SELECT a.*, u.full_name AS doctor_name FROM appointments a JOIN doctors d ON d.id=a.doctor_id "
        "JOIN users u ON u.id=d.user_id WHERE a.patient_id=? ORDER BY a.appt_date DESC, a.appt_time DESC", (pid,)).fetchall()
    consults = db.execute(
        "SELECT c.*, u.full_name AS doctor_name, a.appt_date FROM consultations c JOIN doctors d ON d.id=c.doctor_id "
        "JOIN users u ON u.id=d.user_id JOIN appointments a ON a.id=c.appointment_id "
        "WHERE c.patient_id=? ORDER BY c.created_at DESC", (pid,)).fetchall()
    return render_template("patients/view.html", p=p, appts=appts, consults=consults)


@bp.route("/<int:pid>/edit", methods=["GET", "POST"])
@roles_required("admin", "receptionist")
def edit(pid):
    db = get_db()
    p = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    if request.method == "POST":
        data = _form()
        errors = _validate(data)
        if errors:
            for e in errors:
                flash(e, "danger")
            data["id"], data["patient_no"] = pid, p["patient_no"]
            return render_template("patients/form.html", p=data, editing=True, blood_options=BLOOD)
        db.execute(
            "UPDATE patients SET full_name=?, gender=?, date_of_birth=?, phone=?, email=?, address=?, national_id=?,"
            " blood_group=?, allergies=?, next_of_kin=?, next_of_kin_phone=? WHERE id=?",
            (data["full_name"], data["gender"], data["date_of_birth"] or None, data["phone"], data["email"] or None,
             data["address"], data["national_id"] or None, data["blood_group"] or None, data["allergies"],
             data["next_of_kin"], data["next_of_kin_phone"], pid))
        db.commit()
        flash("Patient updated.", "success")
        return redirect(url_for("patients.view", pid=pid))
    return render_template("patients/form.html", p=p, editing=True, blood_options=BLOOD)


@bp.route("/<int:pid>/delete", methods=["POST"])
@roles_required("admin")
def delete(pid):
    db = get_db()
    if db.execute("SELECT 1 FROM appointments WHERE patient_id=?", (pid,)).fetchone():
        flash("Cannot delete a patient who has appointments or medical history.", "danger")
        return redirect(url_for("patients.view", pid=pid))
    db.execute("DELETE FROM patients WHERE id=?", (pid,))
    db.commit()
    flash("Patient deleted.", "info")
    return redirect(url_for("patients.index"))
