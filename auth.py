import hashlib
import secrets
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from db import get_db
from security import login_required
import mailer


bp = Blueprint("auth", __name__)


# ---------------------------------------------------------
# SAFE REDIRECT
# ---------------------------------------------------------

def _safe_next(target):
    """
    Prevent open redirects by allowing only local paths.
    """

    if (
        target
        and target.startswith("/")
        and not target.startswith("//")
    ):
        return target

    return url_for("dashboard.index")


# ---------------------------------------------------------
# LOGIN - USERNAME OR EMAIL
# ---------------------------------------------------------

@bp.route("/login", methods=["GET", "POST"])
def login():

    if g.user:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":

        identifier = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = get_db()

        # Allow login using either username or email.
        user = db.execute(
            """
            SELECT *
            FROM users
            WHERE username = ? COLLATE NOCASE
               OR email = ? COLLATE NOCASE
            LIMIT 1
            """,
            (identifier, identifier)
        ).fetchone()

        # Verify account status and password.
        if (
            user
            and user["is_active"]
            and check_password_hash(
                user["password_hash"],
                password
            )
        ):

            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]

            return redirect(
                _safe_next(request.args.get("next"))
            )

        flash(
            "Invalid username/email or password.",
            "danger"
        )

    return render_template("login.html")


# ---------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------

@bp.route("/logout", methods=["POST"])
def logout():

    session.clear()

    flash(
        "You have been signed out.",
        "info"
    )

    return redirect(url_for("auth.login"))


# ---------------------------------------------------------
# CHANGE PASSWORD
# ---------------------------------------------------------

@bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():

    if request.method == "POST":

        current = request.form.get("current", "")
        new = request.form.get("new", "")
        confirm = request.form.get("confirm", "")

        if not check_password_hash(
            g.user["password_hash"],
            current
        ):

            flash(
                "Current password is incorrect.",
                "danger"
            )

        elif len(new) < 8:

            flash(
                "New password must be at least 8 characters.",
                "danger"
            )

        elif new != confirm:

            flash(
                "Passwords do not match.",
                "danger"
            )

        elif new == current:

            flash(
                "Choose a password different from the current one.",
                "danger"
            )

        else:

            db = get_db()

            db.execute(
                """
                UPDATE users
                SET password_hash = ?,
                    must_change_password = 0
                WHERE id = ?
                """,
                (
                    generate_password_hash(new),
                    g.user["id"]
                )
            )

            db.commit()

            flash(
                "Password updated.",
                "success"
            )

            return redirect(url_for("dashboard.index"))

    return render_template("change_password.html")


# ---------------------------------------------------------
# FORGOT PASSWORD
# Supports username or email.
# Sends reset link to the registered email address.
# ---------------------------------------------------------

@bp.route("/forgot", methods=["GET", "POST"])
def forgot():

    if request.method == "POST":

        ident = request.form.get(
            "identifier",
            ""
        ).strip()

        db = get_db()

        user = db.execute(
            """
            SELECT *
            FROM users
            WHERE is_active = 1
              AND (
                    username = ? COLLATE NOCASE
                    OR email = ? COLLATE NOCASE
              )
            LIMIT 1
            """,
            (ident, ident)
        ).fetchone()

        if user and user["email"]:

            # Generate a secure reset token.
            token = secrets.token_urlsafe(32)

            # Invalidate previous unused reset tokens.
            db.execute(
                """
                UPDATE password_resets
                SET used = 1
                WHERE user_id = ?
                """,
                (user["id"],)
            )

            # Store only the SHA-256 hash of the token.
            db.execute(
                """
                INSERT INTO password_resets
                (user_id, token_hash, expires_at)
                VALUES (?, ?, ?)
                """,
                (
                    user["id"],
                    hashlib.sha256(
                        token.encode()
                    ).hexdigest(),
                    (
                        datetime.utcnow()
                        + timedelta(hours=1)
                    ).isoformat()
                )
            )

            db.commit()

            # Generate password reset URL.
            link = (
                current_app.config["BASE_URL"]
                + url_for(
                    "auth.reset",
                    token=token
                )
            )

            # Send reset email.
            mailer.password_reset(
                current_app._get_current_object(),
                user,
                link
            )

        # Same message whether or not account exists.
        # This prevents user enumeration.

        flash(
            "If that account exists and has an email address, "
            "a reset link has been sent.",
            "info"
        )

        return redirect(url_for("auth.login"))

    return render_template("forgot.html")


# ---------------------------------------------------------
# RESET PASSWORD
# ---------------------------------------------------------

@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):

    db = get_db()

    # Hash the supplied token before checking the database.
    token_hash = hashlib.sha256(
        token.encode()
    ).hexdigest()

    row = db.execute(
        """
        SELECT *
        FROM password_resets
        WHERE token_hash = ?
          AND used = 0
        """,
        (token_hash,)
    ).fetchone()

    # Check whether token exists and has not expired.
    if (
        not row
        or datetime.fromisoformat(
            row["expires_at"]
        ) < datetime.utcnow()
    ):

        flash(
            "This reset link is invalid or has expired.",
            "danger"
        )

        return redirect(
            url_for("auth.forgot")
        )

    if request.method == "POST":

        new = request.form.get("new", "")
        confirm = request.form.get("confirm", "")

        if len(new) < 8:

            flash(
                "Password must be at least 8 characters.",
                "danger"
            )

        elif new != confirm:

            flash(
                "Passwords do not match.",
                "danger"
            )

        else:

            # Update password.
            db.execute(
                """
                UPDATE users
                SET password_hash = ?,
                    must_change_password = 0
                WHERE id = ?
                """,
                (
                    generate_password_hash(new),
                    row["user_id"]
                )
            )

            # Mark reset token as used.
            db.execute(
                """
                UPDATE password_resets
                SET used = 1
                WHERE id = ?
                """,
                (row["id"],)
            )

            db.commit()

            flash(
                "Password reset. You can sign in now.",
                "success"
            )

            return redirect(
                url_for("auth.login")
            )

    return render_template(
        "reset.html",
        token=token
    )
