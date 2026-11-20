import re
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from db import get_db
from security import roles_required
import mailer

bp = Blueprint("email_admin", __name__, url_prefix="/email")


@bp.route("/", methods=["GET", "POST"])
@roles_required("admin")
def index():
    cfg = current_app.config
    if request.method == "POST":
        to = request.form.get("to", "").strip()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", to):
            flash("Enter a valid email address.", "danger")
        else:
            mailer.send_email(current_app._get_current_object(), to, "Test email from HMS",
                              "<p>If you are reading this, your email setup is working.</p>", kind="test", wait=True)
            flash("Test email queued - check the log below for the result.", "info")
        return redirect(url_for("email_admin.index"))
    logs = get_db().execute("SELECT * FROM email_log ORDER BY id DESC LIMIT 100").fetchall()
    summary = {
        "backend": cfg["MAIL_BACKEND"], "enabled": cfg["MAIL_ENABLED"],
        "from": f'{cfg["MAIL_FROM_NAME"]} <{cfg["MAIL_FROM_ADDRESS"]}>',
    }
    return render_template("email/index.html", logs=logs, s=summary)
