"""Authentication helpers, role checks and CSRF protection."""
import functools
import hmac
import secrets
from flask import abort, g, redirect, request, session, url_for, flash
from db import get_db


def load_user():
    uid = session.get("user_id")
    g.user = None
    g.doctor = None
    if uid:
        user = get_db().execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (uid,)).fetchone()
        if user is None:
            session.clear()
        else:
            g.user = user
            if user["role"] == "doctor":
                g.doctor = get_db().execute("SELECT * FROM doctors WHERE user_id = ?", (uid,)).fetchone()


def login_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        if g.user["must_change_password"] and request.endpoint not in ("auth.change_password", "auth.logout", "static"):
            flash("Please set a new password to continue.", "warning")
            return redirect(url_for("auth.change_password"))
        return view(*a, **kw)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @functools.wraps(view)
        @login_required
        def wrapped(*a, **kw):
            if g.user["role"] not in roles:
                abort(403)
            return view(*a, **kw)
        return wrapped
    return decorator


# ---- CSRF ---------------------------------------------------------------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def csrf_protect():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("_csrf", "")
        if not sent or not expected or not hmac.compare_digest(sent, expected):
            abort(400, "Invalid or missing CSRF token. Refresh the page and try again.")
