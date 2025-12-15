# app.py
# =========================================================
# Digital Facial Recognition Attendance System
# FINAL CLEAN VERSION (SQLAlchemy + Pandas + MySQL)
# =========================================================

import os
import io
import json
import threading
import datetime
import time
from urllib.parse import quote_plus

from flask import Flask, render_template, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from dotenv import load_dotenv
import pandas as pd

from model import (
    train_model_background,
    extract_embedding_for_image,
    load_model_if_exists,
    predict_with_model
)

# ---------------------------------------------------------
# LOAD display and buzzer 
# ---------------------------------------------------------
from hardware import (
    attendance_success,
    attendance_duplicate,
    attendance_unknown
)

# ---------------------------------------------------------
# COOLDOWN CONFIG
# ---------------------------------------------------------
COOLDOWN_SECONDS = {
    "success": 5,
    "duplicate": 5,
    "unknown": 3
}

cooldown_tracker = {}  # { key: last_trigger_timestamp }


# ---------------------------------------------------------
# LOAD ENVIRONMENT VARIABLES
# ---------------------------------------------------------
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = quote_plus(os.getenv("DB_PASSWORD", ""))  # IMPORTANT
DB_NAME = os.getenv("DB_NAME", "attendance_db")
DB_PORT = os.getenv("DB_PORT", "3306")

# ---------------------------------------------------------
# FLASK APP SETUP
# ---------------------------------------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(APP_DIR, "dataset")
os.makedirs(DATASET_DIR, exist_ok=True)

TRAIN_STATUS_FILE = os.path.join(APP_DIR, "train_status.json")

# ---------------------------------------------------------
# TRAIN STATUS HELPERS
# ---------------------------------------------------------
def write_train_status(data):
    with open(TRAIN_STATUS_FILE, "w") as f:
        json.dump(data, f)

def read_train_status():
    if not os.path.exists(TRAIN_STATUS_FILE):
        return {"running": False, "progress": 0, "message": "Not started"}
    with open(TRAIN_STATUS_FILE, "r") as f:
        return json.load(f)

write_train_status({"running": False, "progress": 0, "message": "Idle"})

# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")

# ---------------------------------------------------------
# DASHBOARD STATS (LAST 30 DAYS)
# ---------------------------------------------------------
@app.route("/attendance_stats")
def attendance_stats():
    try:
        df = pd.read_sql(
            text("SELECT timestamp FROM attendance"),
            db.engine
        )
    except Exception as e:
        app.logger.error(f"Stats DB error: {e}")
        return jsonify({"error": "DB error"}), 500

    today = datetime.date.today()
    days = [today - datetime.timedelta(days=i) for i in range(29, -1, -1)]

    if df.empty:
        return jsonify({
            "dates": [d.strftime("%d-%b") for d in days],
            "counts": [0] * 30
        })

    df["date"] = pd.to_datetime(df["timestamp"]).dt.date

    counts = [(df["date"] == d).sum() for d in days]

    return jsonify({
        "dates": [d.strftime("%d-%b") for d in days],
        "counts": [int(c) for c in counts]
    })

# ---------------------------------------------------------
# ADD STUDENT
# ---------------------------------------------------------
@app.route("/add_student", methods=["GET", "POST"])
def add_student():
    if request.method == "GET":
        return render_template("add_student.html")

    name = request.form.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400

    student_id = f"S{int(datetime.datetime.utcnow().timestamp() * 1000)}"

    db.session.execute(
        text("""
            INSERT INTO users (user_id, name, role, created_at)
            VALUES (:id, :name, 'student', NOW())
        """),
        {"id": student_id, "name": name}
    )
    db.session.commit()

    os.makedirs(os.path.join(DATASET_DIR, student_id), exist_ok=True)

    return jsonify({"student_id": student_id})

# ---------------------------------------------------------
# UPLOAD FACE IMAGES
# ---------------------------------------------------------
@app.route("/upload_face", methods=["POST"])
def upload_face():
    student_id = request.form.get("student_id")
    if not student_id:
        return jsonify({"error": "student_id required"}), 400

    files = request.files.getlist("images[]")
    folder = os.path.join(DATASET_DIR, student_id)
    os.makedirs(folder, exist_ok=True)

    saved = 0
    for f in files:
        path = os.path.join(folder, f"{datetime.datetime.utcnow().timestamp()}.jpg")
        f.save(path)
        saved += 1

    return jsonify({"saved": saved})

# ---------------------------------------------------------
# TRAIN MODEL
# ---------------------------------------------------------
@app.route("/train_model")
def train_model_route():
    status = read_train_status()
    if status["running"]:
        return jsonify({"status": "already running"}), 202

    write_train_status({"running": True, "progress": 0, "message": "Training started"})

    def progress_cb(p, m):
        write_train_status({"running": True, "progress": p, "message": m})

    threading.Thread(
        target=train_model_background,
        args=(DATASET_DIR, progress_cb),
        daemon=True
    ).start()

    return jsonify({"status": "started"}), 202

@app.route("/train_status")
def train_status():
    return jsonify(read_train_status())

# ---------------------------------------------------------
# MARK ATTENDANCE PAGE
# ---------------------------------------------------------
@app.route("/mark_attendance")
def mark_attendance_page():
    return render_template("mark_attendance.html")

# ---------------------------------------------------------
# FACE RECOGNITION + DUPLICATE SAFE ATTENDANCE
# ---------------------------------------------------------
@app.route("/recognize_face", methods=["POST"])
def recognize_face():
    # ------------------ INPUT VALIDATION ------------------
    if "image" not in request.files:
        return jsonify({
            "recognized": False,
            "status": "error",
            "message": "No image provided"
        }), 400

    # ------------------ FACE EMBEDDING ------------------
    emb = extract_embedding_for_image(request.files["image"].stream)
    if emb is None:
        # Cooldown for UNKNOWN
        now = time.time()
        key = "UNKNOWN"
        if key not in cooldown_tracker or (now - cooldown_tracker[key]) >= COOLDOWN_SECONDS["unknown"]:
            attendance_unknown()
            cooldown_tracker[key] = now

        return jsonify({
            "recognized": False,
            "status": "unknown",
            "message": "No face detected"
        }), 200

    # ------------------ LOAD MODEL ------------------
    clf = load_model_if_exists()
    if clf is None:
        return jsonify({
            "recognized": False,
            "status": "error",
            "message": "Model not trained"
        }), 200

    # ------------------ PREDICTION ------------------
    student_id, conf = predict_with_model(clf, emb)

    if conf < 0.5:
        now = time.time()
        key = "UNKNOWN"
        if key not in cooldown_tracker or (now - cooldown_tracker[key]) >= COOLDOWN_SECONDS["unknown"]:
            attendance_unknown()
            cooldown_tracker[key] = now

        return jsonify({
            "recognized": False,
            "status": "unknown",
            "confidence": float(conf)
        }), 200

    # ------------------ DUPLICATE CHECK ------------------
    today = datetime.date.today()

    exists = db.session.execute(
        text("""
            SELECT 1 FROM attendance
            WHERE student_id = :sid AND DATE(timestamp) = :today
        """),
        {"sid": student_id, "today": today}
    ).fetchone()

    # ------------------ FETCH STUDENT NAME ------------------
    name = db.session.execute(
        text("SELECT name FROM users WHERE user_id = :sid"),
        {"sid": student_id}
    ).scalar()

    now = time.time()
    key = student_id

    # ------------------ NEW ATTENDANCE ------------------
    if not exists:
        db.session.execute(
            text("""
                INSERT INTO attendance (student_id, class_id, timestamp, status)
                VALUES (:sid, 1, NOW(), 'present')
            """),
            {"sid": student_id}
        )
        db.session.commit()

        # Cooldown check for SUCCESS
        if key not in cooldown_tracker or (now - cooldown_tracker[key]) >= COOLDOWN_SECONDS["success"]:
            attendance_success(name, conf)
            cooldown_tracker[key] = now

        return jsonify({
            "recognized": True,
            "status": "success",
            "student_id": student_id,
            "name": name,
            "confidence": float(conf)
        })

    # ------------------ DUPLICATE ------------------
    if key not in cooldown_tracker or (now - cooldown_tracker[key]) >= COOLDOWN_SECONDS["duplicate"]:
        attendance_duplicate()
        cooldown_tracker[key] = now

    return jsonify({
        "recognized": True,
        "status": "duplicate",
        "student_id": student_id,
        "name": name,
        "confidence": float(conf)
    })


# ---------------------------------------------------------
# ATTENDANCE RECORDS
# ---------------------------------------------------------
@app.route("/attendance_record")
def attendance_record():
    period = request.args.get("period", "all")

    condition = ""
    if period == "daily":
        condition = "WHERE DATE(timestamp) = CURDATE()"
    elif period == "weekly":
        condition = "WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
    elif period == "monthly":
        condition = "WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)"

    rows = db.session.execute(
        text(f"""
            SELECT attendance_id, student_id, timestamp, status
            FROM attendance
            {condition}
            ORDER BY timestamp DESC
        """)
    ).fetchall()

    return render_template("attendance_record.html", records=rows, period=period)

# ---------------------------------------------------------
# CSV DOWNLOAD
# ---------------------------------------------------------
@app.route("/download_csv")
def download_csv():
    rows = db.session.execute(
        text("""
            SELECT attendance_id, student_id, timestamp, status
            FROM attendance
            ORDER BY timestamp DESC
        """)
    ).fetchall()

    output = io.StringIO()
    output.write("attendance_id,student_id,timestamp,status\n")
    for r in rows:
        output.write(",".join(map(str, r)) + "\n")

    mem = io.BytesIO(output.getvalue().encode())
    mem.seek(0)
    return send_file(mem, download_name="attendance.csv", as_attachment=True)

# ---------------------------------------------------------
# RUN APP
# ---------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=False)
