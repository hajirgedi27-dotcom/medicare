import os
from datetime import datetime
from flask import Flask, g, render_template
import db
from config import Config
from security import load_user, csrf_protect, csrf_token


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if config:
        app.config.update(config)
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)

    db.init_app(app)

    # Create tables automatically on first run
    with app.app_context():
        db.init_db()

    app.before_request(load_user)
    app.before_request(csrf_protect)
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.context_processor
    def inject_globals():
        return {"hospital_name": app.config["HOSPITAL_NAME"], "now": datetime.now()}

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Cache-Control"] = "no-store" if g.get("user") else resp.headers.get("Cache-Control", "no-cache")
        return resp

    from blueprints import auth, dashboard, patients, doctors, departments, users, appointments, consultations, email_admin
    for m in (auth, dashboard, patients, doctors, departments, users, appointments, consultations, email_admin):
        app.register_blueprint(m.bp)

    for code, title in ((400, "Bad request"), (403, "Access denied"), (404, "Page not found"), (500, "Server error")):
        app.register_error_handler(code, lambda e, c=code, t=title: (render_template("error.html", code=c, title=t, e=e), c))

    from blueprints.appointments import register_cli
    register_cli(app)
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
