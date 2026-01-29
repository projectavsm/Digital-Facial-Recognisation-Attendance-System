# =========================================================
# Digital Facial Recognition Attendance System
# FINAL PRODUCTION VERSION
# =========================================================

import os
import io
import json
import threading
import datetime
import time
import shutil
from urllib.parse import quote_plus

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from dotenv import load_dotenv
import pandas as pd
from flask import send_from_directory

# AI Model Logic
from model import (
    train_model_background,
    extract_embedding_for_image,
    load_model_if_exists,
    predict_with_model
)

# Hardware Feedback (Buzzer/Display)
from hardware import (
    attendance_success,
    attendance_duplicate,
    attendance_unknown
)

# ---------------------------------------------------------
# INITIAL CONFIGURATION
# ---------------------------------------------------------
load_dotenv()

COOLDOWN_SECONDS = {"success": 5, "duplicate": 5, "unknown": 3}
cooldown_tracker = {}  # Stores last trigger time per student/status

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", "admin_access_key_123")

# Database Setup
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = quote_plus(os.getenv("DB_PASSWORD", ""))
DB_NAME = os.getenv("DB_NAME", "attendance_db")
DB_PORT = os.getenv("DB_PORT", "3306")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Path Setup
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(APP_DIR, "dataset")
TRAIN_STATUS_FILE = os.path.join(APP_DIR, "train_status.json")
os.makedirs(DATASET_DIR, exist_ok=True)

# ---------------------------------------------------------
# HELPERS
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
# CORE ROUTES
# ---------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/attendance_stats")
def attendance_stats():
    """Generates data for the Dashboard Chart (Last 30 Days)"""
    try:
        df = pd.read_sql(text("SELECT timestamp FROM attendance"), db.engine)
        today = datetime.date.today()
        days = [today - datetime.timedelta(days=i) for i in range(29, -1, -1)]
        
        if df.empty:
            return jsonify({"dates": [d.strftime("%d-%b") for d in days], "counts": [0] * 30})

        df["date"] = pd.to_datetime(df["timestamp"]).dt.date
        counts = [(df["date"] == d).sum() for d in days]
        return jsonify({"dates": [d.strftime("%d-%b") for d in days], "counts": [int(c) for c in counts]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------
# STUDENT ENROLLMENT
# ---------------------------------------------------------

@app.route("/enrollment", methods=["GET", "POST"])
def add_student():
    if request.method == "GET":
        return render_template("add_student.html")

    name = request.form.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400

    student_id = f"S{int(datetime.datetime.utcnow().timestamp() * 1000)}"
    db.session.execute(
        text("INSERT INTO users (user_id, name, role, created_at) VALUES (:id, :name, 'student', NOW())"),
        {"id": student_id, "name": name}
    )
    db.session.commit()
    os.makedirs(os.path.join(DATASET_DIR, student_id), exist_ok=True)
    return jsonify({"student_id": student_id})

@app.route("/upload_face", methods=["POST"])
def upload_face():
    student_id = request.form.get("student_id")
    files = request.files.getlist("images[]")
    folder = os.path.join(DATASET_DIR, student_id)
    
    saved = 0
    for f in files:
        path = os.path.join(folder, f"{datetime.datetime.utcnow().timestamp()}.jpg")
        f.save(path)
        saved += 1
    return jsonify({"saved": saved})

# ---------------------------------------------------------
# AI TRAINING
# ---------------------------------------------------------

@app.route("/train_model")
def train_model_route():
    status = read_train_status()
    if status["running"]:
        return jsonify({"status": "already running"}), 202

    def progress_cb(p, m):
        write_train_status({"running": True, "progress": p, "message": m})

    threading.Thread(target=train_model_background, args=(DATASET_DIR, progress_cb), daemon=True).start()
    return jsonify({"status": "started"}), 202

@app.route("/train_status")
def train_status():
    return jsonify(read_train_status())

# ---------------------------------------------------------
# ATTENDANCE LOGIC (THE RECOGNIZER)
# ---------------------------------------------------------

@app.route("/mark_attendance")
def mark_attendance_page():
    return render_template("mark_attendance.html")

@app.route("/recognize_face", methods=["POST"])
def recognize_face():
    if "image" not in request.files:
        return jsonify({"recognized": False, "status": "error", "message": "No image"}), 400

    # 1. Extract Face Embedding
    emb = extract_embedding_for_image(request.files["image"].stream)
    now = time.time()

    if emb is None:
        if "UNKNOWN" not in cooldown_tracker or (now - cooldown_tracker["UNKNOWN"]) >= COOLDOWN_SECONDS["unknown"]:
            attendance_unknown()
            cooldown_tracker["UNKNOWN"] = now
        return jsonify({"recognized": False, "status": "unknown"}), 200

    # 2. Predict using trained model
    clf = load_model_if_exists()
    if clf is None:
        return jsonify({"recognized": False, "status": "error", "message": "Not trained"}), 200

    student_id, conf = predict_with_model(clf, emb)

    # 3. Handle Threshold
    if conf < 0.5:
        if "UNKNOWN" not in cooldown_tracker or (now - cooldown_tracker["UNKNOWN"]) >= COOLDOWN_SECONDS["unknown"]:
            attendance_unknown()
            cooldown_tracker["UNKNOWN"] = now
        return jsonify({"recognized": False, "status": "unknown", "confidence": float(conf)}), 200

    # 4. Success / Duplicate Logic
    name = db.session.execute(text("SELECT name FROM users WHERE user_id = :sid"), {"sid": student_id}).scalar()
    exists = db.session.execute(
        text("SELECT 1 FROM attendance WHERE student_id = :sid AND DATE(timestamp) = CURDATE()"),
        {"sid": student_id}
    ).fetchone()

    if not exists:
        db.session.execute(
            text("INSERT INTO attendance (student_id, class_id, timestamp, status) VALUES (:sid, 1, NOW(), 'present')"),
            {"sid": student_id}
        )
        db.session.commit()
        if student_id not in cooldown_tracker or (now - cooldown_tracker[student_id]) >= COOLDOWN_SECONDS["success"]:
            attendance_success(name, conf)
            cooldown_tracker[student_id] = now
        return jsonify({"recognized": True, "status": "success", "name": name, "confidence": float(conf)})

    # Duplicate detected
    if student_id not in cooldown_tracker or (now - cooldown_tracker[student_id]) >= COOLDOWN_SECONDS["duplicate"]:
        attendance_duplicate()
        cooldown_tracker[student_id] = now
    return jsonify({"recognized": True, "status": "duplicate", "name": name})

# ---------------------------------------------------------
# ADMIN PANEL (PROTECTED)
# ---------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == "admin123":
            session['admin_logged_in'] = True
            return redirect(url_for('admin_directory'))
        return "<h1>Invalid Password</h1><a href='/admin/login'>Try Again</a>", 401
    return render_template("login.html")

@app.route("/admin/directory")
def admin_directory():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    students = db.session.execute(text("SELECT user_id, name, class, section FROM users WHERE role = 'student'")).fetchall()
    return render_template("admin_directory.html", students=students)

@app.route("/admin/view/<student_id>")
def admin_view_student(student_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    res = db.session.execute(text("SELECT name FROM users WHERE user_id = :sid"), {"sid": student_id}).fetchone()
    if not res:
        return redirect(url_for('admin_directory'))

    folder_path = os.path.join(DATASET_DIR, student_id)
    images = [f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.png'))] if os.path.exists(folder_path) else []
    return render_template("admin_view.html", student_id=student_id, student_name=res[0], images=sorted(images))

@app.route("/admin/delete/<student_id>", methods=["POST"])
def delete_student(student_id):
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        db.session.execute(text("DELETE FROM attendance WHERE student_id = :sid"), {"sid": student_id})
        db.session.execute(text("DELETE FROM users WHERE user_id = :sid"), {"sid": student_id})
        db.session.commit()
        
        folder_path = os.path.join(DATASET_DIR, student_id)
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)
        return redirect(url_for('admin_directory'))
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route("/admin/logout")
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

# ---------------------------------------------------------
# DATA EXPORT
# ---------------------------------------------------------

@app.route("/attendance_record")
def attendance_record():
    period = request.args.get("period", "all")
    condition = ""
    if period == "daily": condition = "WHERE DATE(timestamp) = CURDATE()"
    elif period == "weekly": condition = "WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
    
    rows = db.session.execute(text(f"SELECT attendance_id, student_id, timestamp, status FROM attendance {condition} ORDER BY timestamp DESC")).fetchall()
    return render_template("attendance_record.html", records=rows, period=period)

@app.route("/download_csv")
def download_csv():
    rows = db.session.execute(text("SELECT * FROM attendance ORDER BY timestamp DESC")).fetchall()
    output = io.StringIO()
    output.write("id,student_id,timestamp,status\n")
    for r in rows:
        output.write(",".join(map(str, r)) + "\n")
    
    mem = io.BytesIO(output.getvalue().encode())
    mem.seek(0)
    return send_file(mem, download_name="attendance.csv", as_attachment=True)


# ---------------------------------------------------------
# ADMIN TRAINING TRIGGER
# ---------------------------------------------------------

@app.route("/admin/train_trigger", methods=["POST"])
def admin_train_trigger():
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    
    status = read_train_status()
    if status["running"]:
        return jsonify({"status": "already_running"}), 200

    # Start training in a background thread
    def progress_cb(p, m):
        write_train_status({"running": True, "progress": p, "message": m})

    threading.Thread(
        target=train_model_background,
        args=(DATASET_DIR, progress_cb),
        daemon=True
    ).start()
    
    return jsonify({"status": "started"})


# ---------------------------------------------------------
# SERVE DATASET IMAGES
# --------------------------------------------------------

@app.route("/dataset/<student_id>/<filename>")
def serve_dataset_image(student_id, filename):
    """
    Serves images from the dataset directory so they can be 
    displayed in the admin_view.html template.
    """
    # Security: Only logged-in admins can view these images
    if not session.get('admin_logged_in'):
        return "Unauthorized", 401
        
    student_folder = os.path.join(DATASET_DIR, student_id)
    return send_from_directory(student_folder, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)