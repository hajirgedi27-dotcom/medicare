import sqlite3
import re
from datetime import date, datetime, timedelta
import click
from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, url_for, abort
from db import get_db
from security import login_required, roles_required
import mailer

bp = Blueprint("appointments", __name__, url_prefix="/appointments")
PER_PAGE = 20
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DETAIL_Q = (
    "SELECT a.*, p.full_name AS patient_name, p.email AS patient_email, p.patient_no, "
    "u.full_name AS doctor_name, u.email AS doctor_email, dep.name AS department "
    "FROM appointments a JOIN patients p ON p.id=a.patient_id JOIN doctors d ON d.id=a.doctor_id "
    "JOIN users u ON u.id=d.user_id LEFT JOIN departments dep ON dep.id=d.department_id ")


def free_slots(db, doctor_id, day):
    """Return available slots from this doctor's schedule for the selected day."""
    try:
        weekday = datetime.strptime(day, "%Y-%m-%d").weekday()
    except (TypeError, ValueError):
        return []
    schedule = db.execute(
        "SELECT start_time, end_time FROM doctor_schedule "
        "WHERE doctor_id=? AND weekday=? AND enabled=1",
        (doctor_id, weekday),
    ).fetchone()
    if not schedule:
        return []

    start = datetime.strptime(schedule["start_time"], "%H:%M")
    end = datetime.strptime(schedule["end_time"], "%H:%M")
    interval = int(current_app.config["SLOT_MINUTES"])
    if interval <= 0:
        return []

    taken = {r[0] for r in db.execute(
        "SELECT appt_time FROM appointments WHERE doctor_id=? AND appt_date=? AND status<>'cancelled'",
        (doctor_id, day),
    )}
    slots, current = [], start
    while current + timedelta(minutes=interval) <= end:
        value = current.strftime("%H:%M")
        if value not in taken:
            slots.append(value)
        current += timedelta(minutes=interval)

    if day == date.today().isoformat():
        now = datetime.now().strftime("%H:%M")
        slots = [slot for slot in slots if slot > now]
    return slots


def get_detail(db, aid):
    row = db.execute(DETAIL_Q + "WHERE a.id=?", (aid,)).fetchone()
    return dict(row) if row else None


@bp.route("/")
@login_required
def index():
    db = get_db()
    day = request.args.get("date", "")
    status = request.args.get("status", "")
    doctor = request.args.get("doctor", "")
    q = request.args.get("q", "").strip()
    page = max(int(request.args.get("page", 1) or 1), 1)
    where, args = [], []
    if g.user["role"] == "doctor":
        where.append("a.doctor_id=?"); args.append(g.doctor["id"])
    elif doctor:
        where.append("a.doctor_id=?"); args.append(doctor)
    if day:
        where.append("a.appt_date=?"); args.append(day)
    if status:
        where.append("a.status=?"); args.append(status)
    if q:
        where.append("(p.full_name LIKE ? OR p.patient_no LIKE ? OR p.phone LIKE ?)"); args += [f"%{q}%"] * 3
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = db.execute(f"SELECT COUNT(*) FROM appointments a JOIN patients p ON p.id=a.patient_id {clause}", args).fetchone()[0]
    rows = db.execute(DETAIL_Q + clause + " ORDER BY a.appt_date DESC, a.appt_time DESC LIMIT ? OFFSET ?",
                      args + [PER_PAGE, (page - 1) * PER_PAGE]).fetchall()
    doctors = db.execute("SELECT d.id, u.full_name FROM doctors d JOIN users u ON u.id=d.user_id ORDER BY u.full_name").fetchall()
    return render_template("appointments/list.html", rows=rows, day=day, status=status, doctor=doctor, q=q,
                           doctors=doctors, page=page, pages=max((total + PER_PAGE - 1) // PER_PAGE, 1), total=total,
                           today=date.today().isoformat())


@bp.route("/slots")
@login_required
def slots():
    """JSON list of free slots for a doctor on a date (used by the booking form)."""
    day, did = request.args.get("date", ""), request.args.get("doctor_id", "")
    try:
        datetime.strptime(day, "%Y-%m-%d")
        did = int(did)
    except (ValueError, TypeError):
        return jsonify([])
    if day < date.today().isoformat():
        return jsonify([])
    return jsonify(free_slots(get_db(), did, day))


@bp.route("/new", methods=["GET", "POST"])
@roles_required("admin", "receptionist")
def create():
    db = get_db()
    doctors = db.execute(
        "SELECT d.id, u.full_name, dep.name AS department FROM doctors d JOIN users u ON u.id=d.user_id "
        "LEFT JOIN departments dep ON dep.id=d.department_id WHERE u.is_active=1 ORDER BY u.full_name").fetchall()
    patients = db.execute("SELECT id, patient_no, full_name, phone, email FROM patients ORDER BY full_name").fetchall()
    form = {"patient_id": request.args.get("patient_id", ""), "doctor_id": "", "appt_date": date.today().isoformat(),
            "appt_time": "", "reason": ""}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        err = None
        try:
            datetime.strptime(form["appt_date"], "%Y-%m-%d")
        except ValueError:
            err = "Choose a valid date."
        if not err and form["appt_date"] < date.today().isoformat():
            err = "You cannot book an appointment in the past."
        if not err and form["appt_time"] not in free_slots(db, form["doctor_id"], form["appt_date"]):
            err = "That doctor is not available at the selected time. Please choose one of the available slots."
        if not err and form["appt_date"] == date.today().isoformat() and form["appt_time"] <= datetime.now().strftime("%H:%M"):
            err = "That time has already passed."
        patient = None
        if not err:
            patient = db.execute("SELECT id, email FROM patients WHERE id=?", (form["patient_id"],)).fetchone()
            if not patient:
                err = "Select a patient."
            elif not patient["email"] or not EMAIL_RE.match(patient["email"]):
                err = "This patient does not have a valid email address. Update the patient's record before booking so the confirmation can be sent."
        if not err and not db.execute("SELECT 1 FROM doctors d JOIN users u ON u.id=d.user_id WHERE d.id=? AND u.is_active=1", (form["doctor_id"],)).fetchone():
            err = "Select a doctor."
        if not err and db.execute(
                "SELECT 1 FROM appointments WHERE patient_id=? AND appt_date=? AND appt_time=? AND status<>'cancelled'",
                (form["patient_id"], form["appt_date"], form["appt_time"])).fetchone():
            err = "This patient already has an appointment at that time."
        if err:
            flash(err, "danger")
        else:
            try:
                cur = db.execute(
                    "INSERT INTO appointments (patient_id, doctor_id, appt_date, appt_time, reason, created_by) VALUES (?,?,?,?,?,?)",
                    (form["patient_id"], form["doctor_id"], form["appt_date"], form["appt_time"], form["reason"], g.user["id"]))
                db.commit()
            except sqlite3.IntegrityError:
                db.rollback()
                flash("Sorry, that slot was just taken. Please choose another time.", "danger")
            else:
                mailer.appointment_booked(current_app._get_current_object(), get_detail(db, cur.lastrowid))
                flash(f"Appointment booked. A confirmation email has been queued for {patient['email']}.", "success")
                return redirect(url_for("appointments.index", date=form["appt_date"]))
    patient_options = [(p["id"], f'{p["patient_no"]} – {p["full_name"]} ({p["email"] or "No email on record"})') for p in patients]
    doctor_options = [(d["id"], f'Dr. {d["full_name"]}' + (f' – {d["department"]}' if d["department"] else "")) for d in doctors]
    return render_template("appointments/form.html", form=form, patient_options=patient_options, doctor_options=doctor_options)


@bp.route("/<int:aid>/cancel", methods=["POST"])
@login_required
def cancel(aid):
    db = get_db()
    appt = get_detail(db, aid)
    if not appt:
        abort(404)
    if g.user["role"] == "doctor" and appt["doctor_id"] != g.doctor["id"]:
        abort(403)
    if appt["status"] != "scheduled":
        flash("Only scheduled appointments can be cancelled.", "danger")
    else:
        reason = request.form.get("cancel_reason", "").strip()
        db.execute("UPDATE appointments SET status='cancelled', cancel_reason=? WHERE id=?", (reason, aid))
        db.commit()
        appt["cancel_reason"] = reason
        mailer.appointment_cancelled(current_app._get_current_object(), appt)
        flash("Appointment cancelled.", "info")
    return redirect(request.referrer or url_for("appointments.index"))


def register_cli(app):
    @app.cli.command("send-reminders")
    def send_reminders():
        """Email patients about tomorrow's appointments. Schedule daily with cron / Task Scheduler."""
        db = get_db()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        rows = db.execute(DETAIL_Q + "WHERE a.appt_date=? AND a.status='scheduled' AND a.reminder_sent=0", (tomorrow,)).fetchall()
        sent = 0
        for r in rows:
            if mailer.appointment_reminder(app, dict(r)):
                sent += 1
                db.execute("UPDATE appointments SET reminder_sent=1 WHERE id=?", (r["id"],))
        db.commit()
        import time; time.sleep(2)  # let background threads finish logging
        click.echo(f"Queued {sent} reminder(s) for {tomorrow}.")
