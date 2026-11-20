from datetime import date
from flask import Blueprint, flash, g, redirect, render_template, request, url_for, abort
from db import get_db
from security import login_required, roles_required
from blueprints.appointments import get_detail

bp = Blueprint("consultations", __name__, url_prefix="/consultations")


@bp.route("/appointment/<int:aid>", methods=["GET", "POST"])
@roles_required("doctor")
def record(aid):
    """Doctor records diagnosis + prescription for one of their own appointments."""
    db = get_db()
    appt = get_detail(db, aid)
    if not appt or appt["doctor_id"] != g.doctor["id"]:
        abort(404)
    if appt["status"] == "cancelled":
        flash("This appointment was cancelled.", "danger")
        return redirect(url_for("appointments.index"))
    existing = db.execute("SELECT * FROM consultations WHERE appointment_id=?", (aid,)).fetchone()
    patient = db.execute("SELECT * FROM patients WHERE id=?", (appt["patient_id"],)).fetchone()
    if request.method == "POST":
        symptoms = request.form.get("symptoms", "").strip()
        diagnosis = request.form.get("diagnosis", "").strip()
        prescription = request.form.get("prescription", "").strip()
        notes = request.form.get("notes", "").strip()
        if not diagnosis:
            flash("Diagnosis is required.", "danger")
        else:
            if existing:
                db.execute("UPDATE consultations SET symptoms=?, diagnosis=?, prescription=?, notes=? WHERE id=?",
                           (symptoms, diagnosis, prescription, notes, existing["id"]))
            else:
                db.execute("INSERT INTO consultations (appointment_id, patient_id, doctor_id, symptoms, diagnosis, prescription, notes)"
                           " VALUES (?,?,?,?,?,?,?)", (aid, appt["patient_id"], g.doctor["id"], symptoms, diagnosis, prescription, notes))
            db.execute("UPDATE appointments SET status='completed' WHERE id=?", (aid,))
            db.commit()
            flash("Consultation saved and appointment marked completed.", "success")
            return redirect(url_for("dashboard.index"))
        existing = {"symptoms": symptoms, "diagnosis": diagnosis, "prescription": prescription, "notes": notes}
    return render_template("consultations/form.html", appt=appt, patient=patient, c=existing)


@bp.route("/<int:cid>/print")
@login_required
def print_view(cid):
    db = get_db()
    c = db.execute(
        "SELECT c.*, p.full_name AS patient_name, p.patient_no, p.date_of_birth, p.gender, u.full_name AS doctor_name, "
        "a.appt_date FROM consultations c JOIN patients p ON p.id=c.patient_id JOIN doctors d ON d.id=c.doctor_id "
        "JOIN users u ON u.id=d.user_id JOIN appointments a ON a.id=c.appointment_id WHERE c.id=?", (cid,)).fetchone()
    if not c:
        abort(404)
    if g.user["role"] == "doctor" and c["doctor_id"] != g.doctor["id"]:
        abort(403)
    return render_template("consultations/print.html", c=c)
