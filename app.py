import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, flash, render_template, request
from werkzeug.security import generate_password_hash

APP_ROOT = Path(__file__).parent
DATABASE_PATH = APP_ROOT / "app.db"

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

    connection.commit()

    cursor.execute("SELECT COUNT(*) FROM device_data")
    (device_count,) = cursor.fetchone()
    if device_count == 0:
        seed_data = [
            ("Thermostat", "Temperature", 22.5, datetime.utcnow().isoformat()),
            ("Thermostat", "Humidity", 45.0, datetime.utcnow().isoformat()),
            ("Camera", "Events", 5, datetime.utcnow().isoformat()),
            ("Camera", "Uptime", 99.5, datetime.utcnow().isoformat()),
            ("Sensor", "Air Quality", 12.3, datetime.utcnow().isoformat()),
        ]
        cursor.executemany(
            "INSERT INTO device_data (device_name, metric, value, recorded_at) VALUES (?, ?, ?, ?)",
            seed_data,
        )
        connection.commit()

    connection.close()


init_db()


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
    if selected_device:
        cursor.execute(
            "SELECT device_name, metric, value, recorded_at FROM device_data WHERE device_name = ? ORDER BY recorded_at DESC",
            (selected_device,),
        )
        device_rows = cursor.fetchall()

    connection.close()
    return render_template(
        "dashboard.html",
        devices=devices,
        selected_device=selected_device,
        device_rows=device_rows,
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)