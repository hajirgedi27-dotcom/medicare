# Hospital Management System – Standard Package + Email Add-on

Flask (Python) · SQLite · HTML/CSS/JavaScript

## 1. Run it (5 minutes)

```bash
python -m venv venv
venv\Scripts\activate            # Windows      (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt
python run.py
```
Open http://127.0.0.1:5000 and sign in with **admin / admin123**.
You are forced to choose a new password on first login. The database
(`instance/hms.sqlite`) and 4 sample departments are created automatically.

## 2. What is included

| Feature | Admin | Receptionist | Doctor |
|---|:-:|:-:|:-:|
| Separate logins & role-based access | ✔ | ✔ | ✔ |
| Dashboard statistics | ✔ (full) | ✔ (full) | ✔ (own) |
| Patient registration / edit | ✔ | ✔ | view only |
| Patient search & filtering (name, phone, no., ID, email, gender, blood group) | ✔ | ✔ | ✔ |
| Doctor registration / activate / reset password | ✔ | view | – |
| Department management | ✔ | view | – |
| Staff accounts (admin / receptionist) | ✔ | – | – |
| Book & cancel appointments | ✔ | ✔ | cancel own |
| **Double-booking prevention** (booking form hides taken slots + database unique index) | ✔ | ✔ | – |
| View assigned appointments | ✔ (all) | ✔ (all) | ✔ (own) |
| Record diagnosis & prescription (+ printable prescription) | – | – | ✔ |
| Email & email log page | ✔ | – | – |

Security: hashed passwords, CSRF protection on every form, session cookies
(HttpOnly, SameSite), role checks on every route, forced first-login password
change, parameterised SQL, security headers.

## 3. Email add-on (the KES 500 extra)

Emails sent automatically:

1. **Appointment confirmation** to the patient (if the patient has an email) + alert to the doctor
2. **Appointment cancellation** notice to patient and doctor (includes the reason)
3. **Appointment reminder** the day before (`flask send-reminders`, see below)
4. **Welcome email** with login details when an account is created / password reset by admin
5. **Forgot-password** link (valid 1 hour, single use)
6. **Test email** button + full **email log** (sent / failed + error message) under *Email & Logs*

Emails are sent in a background thread, so the system never slows down or
crashes if the mail server is slow or offline – failures are simply logged.

### Python-only Gmail SMTP configuration

This package sends email directly from Python using the standard-library `smtplib` module. PHP, Composer, PHPMailer, and a separate PHP mailer are not required.

The default backend is `smtp`. Configure these environment variables before starting Flask:

```powershell
$env:MAIL_ENABLED = "true"
$env:MAIL_BACKEND = "smtp"
$env:MAIL_FROM_NAME = "City Care Hospital"
$env:MAIL_FROM_ADDRESS = "rockykim254@gmail.com"
$env:SMTP_HOST = "smtp.gmail.com"
$env:SMTP_PORT = "587"
$env:SMTP_USER = "rockykim254@gmail.com"
$env:SMTP_PASSWORD = "YOUR-NEW-GOOGLE-APP-PASSWORD"
$env:SMTP_SECURITY = "tls"
python run.py
```

Use a Google App Password, not your normal Gmail password. If an App Password has been shared or exposed, revoke it and generate a new one. Keep the replacement private. These PowerShell variables apply to that PowerShell window.

For Gmail, port `587` uses STARTTLS. Port `465` can be used with `SMTP_SECURITY=ssl`. The sender address is set to the authenticated Gmail account because Gmail does not permit arbitrary sender addresses.

The **Email & Logs** page continues to use the same `send_email()` function and records sent/failed attempts. Appointment confirmations, doctor alerts, cancellation notices, reminders, welcome emails, and password-reset messages retain their existing templates and triggers.

## 4. Deploying

* Set a real `SECRET_KEY` and `SESSION_COOKIE_SECURE=True` (HTTPS) as environment variables.
* Run behind a production server, e.g. `pip install gunicorn && gunicorn -w 2 app:app`
  (or `waitress-serve app:app` on Windows), fronted by Nginx/Apache with HTTPS.
* Back up `instance/hms.sqlite` regularly – it is the whole database.
* Change the hospital name with `HOSPITAL_NAME`; working hours/slot length are
  `DAY_START`, `DAY_END`, `SLOT_MINUTES` in `config.py`.

## 5. Project layout

```
app.py            application factory          config.py   all settings
db.py / schema.sql  SQLite + tables            security.py login, roles, CSRF
mailer.py         Python SMTP email add-on + templates
blueprints/       auth, dashboard, patients, doctors, departments,
                  users, appointments, consultations, email_admin
templates/ static/  HTML, CSS, JavaScript
```

## 6. Scope

Included: Standard Package + Email add-on.
Not included (as quoted): patient self-service portal, billing, advanced reporting.


## Doctor appointment availability

Each doctor has an individual weekly schedule. When an administrator creates or edits a doctor, the **Weekly availability** section controls the days and opening/closing times for appointments. Appointment slots are generated in 30-minute intervals inside those hours; existing appointments and past times are excluded.

When this update is first started, doctors already in the database are assigned a default Monday-Friday, 08:00-17:00 schedule if they do not already have one. Administrators can customise those hours under **Doctors → Edit**. Receptionists/admins book appointments from **Appointments → Book appointment**. The patient must have a valid email address on their patient record; after the appointment is saved, the system queues a confirmation to the patient and an alert to the doctor (if the doctor has an email address). Check **Email & Logs** to confirm whether SMTP delivery succeeded or failed.
