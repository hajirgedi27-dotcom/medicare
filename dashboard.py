from datetime import date
from flask import Blueprint, g, render_template
from db import get_db
from security import login_required

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    db = get_db()
    today = date.today().isoformat()
    if g.user["role"] == "doctor":
        did = g.doctor["id"]
        stats = {
            "today": db.execute("SELECT COUNT(*) FROM appointments WHERE doctor_id=? AND appt_date=? AND status='scheduled'", (did, today)).fetchone()[0],
            "upcoming": db.execute("SELECT COUNT(*) FROM appointments WHERE doctor_id=? AND appt_date>? AND status='scheduled'", (did, today)).fetchone()[0],
            "completed": db.execute("SELECT COUNT(*) FROM appointments WHERE doctor_id=? AND status='completed'", (did,)).fetchone()[0],
            "patients": db.execute("SELECT COUNT(DISTINCT patient_id) FROM appointments WHERE doctor_id=?", (did,)).fetchone()[0],
        }
        todays = db.execute(
            "SELECT a.*, p.full_name AS patient_name, p.patient_no FROM appointments a JOIN patients p ON p.id=a.patient_id "
            "WHERE a.doctor_id=? AND a.appt_date=? AND a.status<>'cancelled' ORDER BY a.appt_time", (did, today)).fetchall()
        return render_template("dashboard.html", stats=stats, todays=todays)

    stats = {
        "patients": db.execute("SELECT COUNT(*) FROM patients").fetchone()[0],
        "doctors": db.execute("SELECT COUNT(*) FROM doctors d JOIN users u ON u.id=d.user_id WHERE u.is_active=1").fetchone()[0],
        "departments": db.execute("SELECT COUNT(*) FROM departments").fetchone()[0],
        "today": db.execute("SELECT COUNT(*) FROM appointments WHERE appt_date=? AND status='scheduled'", (today,)).fetchone()[0],
        "upcoming": db.execute("SELECT COUNT(*) FROM appointments WHERE appt_date>? AND status='scheduled'", (today,)).fetchone()[0],
        "completed": db.execute("SELECT COUNT(*) FROM appointments WHERE status='completed'").fetchone()[0],
        "cancelled": db.execute("SELECT COUNT(*) FROM appointments WHERE status='cancelled'").fetchone()[0],
        "new_patients": db.execute("SELECT COUNT(*) FROM patients WHERE created_at >= date('now','-30 day')").fetchone()[0],
    }
    todays = db.execute(
        "SELECT a.*, p.full_name AS patient_name, u.full_name AS doctor_name FROM appointments a "
        "JOIN patients p ON p.id=a.patient_id JOIN doctors d ON d.id=a.doctor_id JOIN users u ON u.id=d.user_id "
        "WHERE a.appt_date=? AND a.status<>'cancelled' ORDER BY a.appt_time", (today,)).fetchall()
    by_dept = db.execute(
        "SELECT COALESCE(dep.name,'Unassigned') AS name, COUNT(*) AS n FROM appointments a JOIN doctors d ON d.id=a.doctor_id "
        "LEFT JOIN departments dep ON dep.id=d.department_id WHERE a.status<>'cancelled' GROUP BY 1 ORDER BY n DESC").fetchall()
    return render_template("dashboard.html", stats=stats, todays=todays, by_dept=by_dept)
