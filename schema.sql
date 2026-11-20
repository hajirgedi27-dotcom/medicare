PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    email         TEXT,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin','receptionist','doctor')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS departments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS doctors (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    specialization TEXT,
    phone         TEXT,
    license_no    TEXT
);

-- Each doctor's recurring weekly availability. weekday: Monday=0 ... Sunday=6.
CREATE TABLE IF NOT EXISTS doctor_schedule (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id   INTEGER NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    weekday     INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    UNIQUE (doctor_id, weekday),
    CHECK (start_time < end_time)
);
CREATE INDEX IF NOT EXISTS idx_doctor_schedule_doctor ON doctor_schedule(doctor_id, weekday);

CREATE TABLE IF NOT EXISTS patients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_no  TEXT NOT NULL UNIQUE,
    full_name   TEXT NOT NULL,
    gender      TEXT CHECK (gender IN ('Male','Female','Other')),
    date_of_birth TEXT,
    phone       TEXT,
    email       TEXT,
    address     TEXT,
    national_id TEXT,
    blood_group TEXT,
    allergies   TEXT,
    next_of_kin TEXT,
    next_of_kin_phone TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_patients_name  ON patients(full_name);
CREATE INDEX IF NOT EXISTS idx_patients_phone ON patients(phone);

CREATE TABLE IF NOT EXISTS appointments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  INTEGER NOT NULL REFERENCES patients(id),
    doctor_id   INTEGER NOT NULL REFERENCES doctors(id),
    appt_date   TEXT NOT NULL,           -- YYYY-MM-DD
    appt_time   TEXT NOT NULL,           -- HH:MM
    reason      TEXT,
    status      TEXT NOT NULL DEFAULT 'scheduled'
                CHECK (status IN ('scheduled','completed','cancelled')),
    cancel_reason TEXT,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    reminder_sent INTEGER NOT NULL DEFAULT 0
);
-- Database-level double-booking prevention: one active appointment per doctor per slot
CREATE UNIQUE INDEX IF NOT EXISTS uq_doctor_slot
    ON appointments(doctor_id, appt_date, appt_time) WHERE status <> 'cancelled';
CREATE INDEX IF NOT EXISTS idx_appt_date ON appointments(appt_date);

CREATE TABLE IF NOT EXISTS consultations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id INTEGER NOT NULL UNIQUE REFERENCES appointments(id),
    patient_id     INTEGER NOT NULL REFERENCES patients(id),
    doctor_id      INTEGER NOT NULL REFERENCES doctors(id),
    symptoms       TEXT,
    diagnosis      TEXT NOT NULL,
    prescription   TEXT,
    notes          TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Email add-on
CREATE TABLE IF NOT EXISTS email_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient  TEXT NOT NULL,
    subject    TEXT NOT NULL,
    kind       TEXT,
    backend    TEXT,
    status     TEXT NOT NULL,            -- sent | failed | skipped
    error      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS password_resets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0
);
