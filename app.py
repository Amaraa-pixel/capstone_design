import os
import smtplib
import sqlite3
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from flask import Flask, flash, jsonify, render_template, request
from werkzeug.security import generate_password_hash

APP_ROOT = Path(__file__).parent
DATABASE_PATH = APP_ROOT / "app.db"
PLUG_DEVICE_NAME = os.getenv("PLUG_DEVICE_NAME", "Tapo P110M Matter Plug")
PLUG_SERIAL = os.getenv("PLUG_SERIAL", "P110M-01")
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "dev-webhook-token")
TOGGLE_WINDOW_SECONDS = int(os.getenv("TOGGLE_WINDOW_SECONDS", "5"))
TOGGLE_THRESHOLD = int(os.getenv("TOGGLE_THRESHOLD", "5"))

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

app = Flask(__name__)
app.secret_key = "dev-secret-key"


def get_db_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            bio TEXT DEFAULT ''
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS device_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_name TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            recorded_at TEXT NOT NULL
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS plug_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial TEXT NOT NULL,
            state TEXT NOT NULL,
            ts TEXT NOT NULL
        );
        """
    )

    connection.commit()

    cursor.execute("DELETE FROM device_data WHERE device_name = ?", ("Camera",))
    connection.commit()

    cursor.execute(
        "UPDATE device_data SET device_name = ? WHERE device_name = ?",
        (PLUG_DEVICE_NAME, "Matter Switch Plug"),
    )
    connection.commit()

    cursor.execute("SELECT COUNT(*) FROM device_data")
    (device_count,) = cursor.fetchone()
    if device_count == 0:
        seed_data = [
            ("Thermostat", "Temperature (°C)", 22.5, datetime.utcnow().isoformat()),
            ("Thermostat", "Humidity (%)", 45.0, datetime.utcnow().isoformat()),
            ("Sensor", "Air Quality", 12.3, datetime.utcnow().isoformat()),
            (PLUG_DEVICE_NAME, "Status", 1, datetime.utcnow().isoformat()),
            (
                PLUG_DEVICE_NAME,
                "Power Usage (W)",
                42.5,
                datetime.utcnow().isoformat(),
            ),
            (
                PLUG_DEVICE_NAME,
                "Energy Today (kWh)",
                1.8,
                datetime.utcnow().isoformat(),
            ),
            (
                PLUG_DEVICE_NAME,
                "Abnormal Activity Alerts",
                3,
                datetime.utcnow().isoformat(),
            ),
            (
                PLUG_DEVICE_NAME,
                "Tampering Alerts",
                1,
                datetime.utcnow().isoformat(),
            ),
            (
                "Motion Sensor",
                "Motion Events",
                3,
                datetime.utcnow().isoformat(),
            ),
            (
                "Motion Sensor",
                "Temperature (°C)",
                21.8,
                datetime.utcnow().isoformat(),
            ),
            (
                "Motion Sensor",
                "Humidity (%)",
                48.2,
                datetime.utcnow().isoformat(),
            ),
            (
                "Motion Sensor",
                "Abnormal Activity Alerts",
                1,
                datetime.utcnow().isoformat(),
            ),
        ]
        cursor.executemany(
            "INSERT INTO device_data (device_name, metric, value, recorded_at) VALUES (?, ?, ?, ?)",
            seed_data,
        )
        connection.commit()

    cursor.execute(
        "SELECT COUNT(*) FROM device_data WHERE device_name = ?",
        (PLUG_DEVICE_NAME,),
    )
    (matter_count,) = cursor.fetchone()
    if matter_count == 0:
        plug_data = [
            (PLUG_DEVICE_NAME, "Status", 1, datetime.utcnow().isoformat()),
            (
                PLUG_DEVICE_NAME,
                "Power Usage (W)",
                42.5,
                datetime.utcnow().isoformat(),
            ),
            (
                PLUG_DEVICE_NAME,
                "Energy Today (kWh)",
                1.8,
                datetime.utcnow().isoformat(),
            ),
            (
                PLUG_DEVICE_NAME,
                "Abnormal Activity Alerts",
                3,
                datetime.utcnow().isoformat(),
            ),
            (
                PLUG_DEVICE_NAME,
                "Tampering Alerts",
                1,
                datetime.utcnow().isoformat(),
            ),
        ]
        cursor.executemany(
            "INSERT INTO device_data (device_name, metric, value, recorded_at) VALUES (?, ?, ?, ?)",
            plug_data,
        )
        connection.commit()

    plug_alert_metrics = {
        "Abnormal Activity Alerts": 3,
        "Tampering Alerts": 1,
    }
    for metric, value in plug_alert_metrics.items():
        cursor.execute(
            "SELECT COUNT(*) FROM device_data WHERE device_name = ? AND metric = ?",
            (PLUG_DEVICE_NAME, metric),
        )
        (existing_count,) = cursor.fetchone()
        if existing_count == 0:
            cursor.execute(
                "INSERT INTO device_data (device_name, metric, value, recorded_at) VALUES (?, ?, ?, ?)",
                (PLUG_DEVICE_NAME, metric, value, datetime.utcnow().isoformat()),
            )
            connection.commit()

    cursor.execute(
        "SELECT COUNT(*) FROM device_data WHERE device_name = ?",
        ("Motion Sensor",),
    )
    (motion_count,) = cursor.fetchone()
    if motion_count == 0:
        motion_data = [
            ("Motion Sensor", "Motion Events", 3, datetime.utcnow().isoformat()),
            ("Motion Sensor", "Temperature (°C)", 21.8, datetime.utcnow().isoformat()),
            ("Motion Sensor", "Humidity (%)", 48.2, datetime.utcnow().isoformat()),
            (
                "Motion Sensor",
                "Abnormal Activity Alerts",
                1,
                datetime.utcnow().isoformat(),
            ),
        ]
        cursor.executemany(
            "INSERT INTO device_data (device_name, metric, value, recorded_at) VALUES (?, ?, ?, ?)",
            motion_data,
        )
        connection.commit()

    cursor.execute(
        "SELECT COUNT(*) FROM plug_state WHERE serial = ?",
        (PLUG_SERIAL,),
    )
    (plug_state_count,) = cursor.fetchone()
    if plug_state_count == 0:
        now = datetime.utcnow().replace(microsecond=0)
        timeline_points = []
        for minutes_ago, state in [
            (45, "off"),
            (35, "on"),
            (25, "off"),
            (15, "on"),
            (5, "off"),
        ]:
            timestamp = (now - timedelta(minutes=minutes_ago)).isoformat()
            timeline_points.append((PLUG_SERIAL, state, timestamp))

        cursor.executemany(
            "INSERT INTO plug_state (serial, state, ts) VALUES (?, ?, ?)",
            timeline_points,
        )
        connection.commit()

    connection.close()


init_db()


def record_plug_state(serial: str, state: str, ts: str):
    """Persist plug timeline state with timestamp."""
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO plug_state (serial, state, ts) VALUES (?, ?, ?)",
        (serial, state, ts),
    )
    connection.commit()
    connection.close()


def record_plug_metrics(
    serial: str,
    state: str,
    ts: str,
    power_w: float | None,
    energy_kwh: float | None,
    tamper: bool | None,
    abnormal: bool | None,
):
    """Persist status metrics for the plug in device_data."""
    connection = get_db_connection()
    cursor = connection.cursor()
    rows = [
        (PLUG_DEVICE_NAME, "Status", 1 if state.lower() == "on" else 0, ts),
    ]
    if power_w is not None:
        rows.append((PLUG_DEVICE_NAME, "Power Usage (W)", float(power_w), ts))
    if energy_kwh is not None:
        rows.append((PLUG_DEVICE_NAME, "Energy Today (kWh)", float(energy_kwh), ts))
    if tamper is not None:
        rows.append((PLUG_DEVICE_NAME, "Tampering Alerts", 1 if tamper else 0, ts))
    if abnormal is not None:
        rows.append((PLUG_DEVICE_NAME, "Abnormal Activity Alerts", 1 if abnormal else 0, ts))

    cursor.executemany(
        "INSERT INTO device_data (device_name, metric, value, recorded_at) VALUES (?, ?, ?, ?)",
        rows,
    )
    connection.commit()
    connection.close()


def record_abnormal_alert(ts: str):
    """Insert an abnormal activity alert metric for the plug."""
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO device_data (device_name, metric, value, recorded_at) VALUES (?, ?, ?, ?)",
        (PLUG_DEVICE_NAME, "Abnormal Activity Alerts", 1, ts),
    )
    connection.commit()
    connection.close()


def send_email_alert(subject: str, body: str):
    """Send an email alert if SMTP configuration is present, otherwise log to console."""
    if not (SMTP_SERVER and SMTP_FROM and ALERT_EMAIL_TO):
        print(f"[alert] {subject}: {body}")
        return

    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = ALERT_EMAIL_TO
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as smtp:
            if SMTP_USE_TLS:
                smtp.starttls()
            if SMTP_USERNAME and SMTP_PASSWORD:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)
    except Exception as exc:  # noqa: BLE001
        print(f"[alert][error] Failed to send email: {exc}")


def detect_toggle_burst(serial: str, ts: str) -> bool:
    """Detect rapid toggling of the plug within the configured window."""
    window_start = (datetime.fromisoformat(ts) - timedelta(seconds=TOGGLE_WINDOW_SECONDS)).isoformat()

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT state, ts FROM plug_state WHERE serial = ? AND ts >= ? ORDER BY ts ASC",
        (serial, window_start),
    )
    rows = cursor.fetchall()
    connection.close()

    if len(rows) < TOGGLE_THRESHOLD:
        return False

    transitions = sum(1 for idx in range(1, len(rows)) if rows[idx]["state"] != rows[idx - 1]["state"])
    return transitions >= TOGGLE_THRESHOLD - 1


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        bio = request.form.get("bio", "").strip()

        if not name or not email or not password:
            flash("Please complete all required fields.")
        else:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            existing = cursor.fetchone()

            if existing:
                flash("This email is already registered.")
            else:
                password_hash = generate_password_hash(password)
                cursor.execute(
                    "INSERT INTO users (name, email, password_hash, bio) VALUES (?, ?, ?, ?)",
                    (name, email, password_hash, bio),
                )
                connection.commit()
                flash("Registration successful! Open the profile page to view your details.")
            connection.close()

    return render_template("register.html")


@app.route("/profile", methods=["GET", "POST"])
def profile():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM users ORDER BY id LIMIT 1")
    user = cursor.fetchone()

    if request.method == "POST":
        if user is None:
            flash("Please register a user first.")
        else:
            name = request.form.get("name", user["name"])
            email = request.form.get("email", user["email"])
            bio = request.form.get("bio", user["bio"])

            cursor.execute(
                "UPDATE users SET name = ?, email = ?, bio = ? WHERE id = ?",
                (name.strip(), email.strip(), bio.strip(), user["id"]),
            )
            connection.commit()
            flash("Profile updated.")
            cursor.execute("SELECT * FROM users WHERE id = ?", (user["id"],))
            user = cursor.fetchone()

    connection.close()
    return render_template("profile.html", user=user)


@app.route("/dashboard")
def dashboard():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT DISTINCT device_name FROM device_data ORDER BY device_name")
    devices = [row[0] for row in cursor.fetchall()]

    selected_device = request.args.get("device") or (devices[0] if devices else None)
    device_rows = []
    abnormal_rows = []
    if selected_device:
        cursor.execute(
            "SELECT device_name, metric, value, recorded_at FROM device_data WHERE device_name = ? ORDER BY recorded_at DESC",
            (selected_device,),
        )
        device_rows = cursor.fetchall()
        abnormal_rows = [
            row
            for row in device_rows
            if (
                ("abnormal" in row["metric"].lower()
                or "tamper" in row["metric"].lower())
                and row["value"] > 0
            )
        ]

    connection.close()
    return render_template(
        "dashboard.html",
        devices=devices,
        selected_device=selected_device,
        device_rows=device_rows,
        abnormal_rows=abnormal_rows,
    )


@app.route("/plug-timeline")
def plug_timeline():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT ts, state FROM plug_state WHERE serial = ? ORDER BY id ASC",
        (PLUG_SERIAL,),
    )
    timeline_rows = cursor.fetchall()
    connection.close()

    return render_template(
        "timeline.html",
        timeline_rows=timeline_rows,
        plug_name=PLUG_DEVICE_NAME,
        plug_serial=PLUG_SERIAL,
    )


@app.route("/api/plug-timeline")
def plug_timeline_api():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT ts, state FROM plug_state WHERE serial = ? ORDER BY id ASC",
        (PLUG_SERIAL,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()
    return jsonify(rows)


@app.route("/api/plug-update", methods=["POST"])
def plug_update():
    payload = request.get_json(silent=True) or {}
    token = request.headers.get("X-Webhook-Token") or payload.get("token")
    if token != WEBHOOK_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    serial = payload.get("serial", PLUG_SERIAL)
    state = payload.get("state")
    if not state:
        return jsonify({"error": "State is required"}), 400

    timestamp = payload.get("ts") or datetime.utcnow().replace(microsecond=0).isoformat()
    power_w = payload.get("power_w")
    energy_kwh = payload.get("energy_kwh")
    tamper = payload.get("tamper")
    abnormal = payload.get("abnormal")

    record_plug_state(serial, state, timestamp)
    record_plug_metrics(serial, state, timestamp, power_w, energy_kwh, tamper, abnormal)

    if detect_toggle_burst(serial, timestamp):
        record_abnormal_alert(timestamp)
        send_email_alert(
            subject=f"{PLUG_DEVICE_NAME} rapid toggling detected",
            body=(
                "The plug was toggled repeatedly within the last "
                f"{TOGGLE_WINDOW_SECONDS} seconds. Please review device behavior."
            ),
        )

    return jsonify({"status": "ok", "recorded_at": timestamp})


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
