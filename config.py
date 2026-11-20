"""Application configuration. Override anything with environment variables
or by editing the defaults below."""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Load environment variables from the project's .env file
load_dotenv(os.path.join(BASE_DIR, ".env"))

def _bool(name, default):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


class Config:
    # ---- Core -------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "CHANGE-ME-before-going-live")
    DATABASE = os.environ.get("DATABASE", os.path.join(BASE_DIR, "instance", "hms.sqlite"))
    HOSPITAL_NAME = os.environ.get("HOSPITAL_NAME", "City Care Hospital")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)  # True when on HTTPS
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 hours

    # Appointment slots
    DAY_START = "08:00"
    DAY_END = "17:00"
    SLOT_MINUTES = 30

    # ---- Email add-on -----------------------------------------------------
    MAIL_ENABLED = _bool("MAIL_ENABLED", True)
    # Python-only email delivery. No PHP bridge is required.
    # Supported backends: smtp (real delivery), console (development).
    MAIL_BACKEND = os.environ.get("MAIL_BACKEND", "smtp").strip().lower()
    MAIL_FROM_NAME = os.environ.get("MAIL_FROM_NAME", HOSPITAL_NAME)
    MAIL_FROM_ADDRESS = os.environ.get("MAIL_FROM_ADDRESS", "rockykim254@gmail.com")
    MAIL_TIMEOUT = int(os.environ.get("MAIL_TIMEOUT", "30"))

    # Gmail SMTP settings. Keep the App Password in an environment variable.
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "rockykim254@gmail.com").strip()
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_SECURITY = os.environ.get("SMTP_SECURITY", "tls").strip().lower()  # tls | ssl | none

    # Public URL used inside emails (password reset links)
    BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
