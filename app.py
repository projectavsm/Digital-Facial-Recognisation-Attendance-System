import os, io, json, threading, datetime, time, shutil
from urllib.parse import quote_plus
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from dotenv import load_dotenv
import pandas as pd

# AI Model Logic (from your model.py)
from model import train_model_background, extract_embedding_for_image, load_model_if_exists

load_dotenv()
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", "admin_access_key_123")

# Database Setup
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = quote_plus(os.getenv("DB_PASSWORD", ""))
DB_NAME = os.getenv("DB_NAME", "attendance_db")
DB_PORT = os.getenv("DB_PORT", "3306")

app.config["SQLALCHEMY_DATABASE_URI"] = f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(APP_DIR, "dataset")
TRAIN_STATUS_FILE = os.path.join(APP_DIR, "train_status.json")
os.makedirs(DATASET_DIR, exist_ok=True)

def write_train_status(data):
    with open(TRAIN_STATUS_FILE, "w") as f: json.dump(data, f)

def read_train_status():
    if not os.path.exists(TRAIN_STATUS_FILE): return {"running": False, "progress": 0, "message": "Idle"}
    with open(TRAIN_STATUS_FILE, "r") as f: return json.load(f)

# --- ROUTES ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/attendance_stats")
def attendance_stats():
    try:
        df = pd.read_sql(text("SELECT timestamp FROM attendance"), db.engine)
        today = datetime.date.today()
        days = [today - datetime.timedelta(days=i) for i in range(29, -1, -1)]
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date
        counts = [(df["date"] == d).sum() for d in days]
        return jsonify({"dates": [d.strftime("%d-%b") for d in days], "counts": [int(c) for c in counts]})
    except: return jsonify({"dates": [], "counts": []})

@app.route("/enrollment", methods=["GET", "POST"])
def add_student():
    if request.method == "GET": return render_template("add_student.html")
    name, s_class, s_section = request.form.get("name"), request.form.get("class"), request.form.get("section")
    student_id = f"S{int(time.time() * 1000)}"
    try:
        db.session.execute(text("INSERT INTO users (user_id, name, class, section, role, created_at) VALUES (:id, :n, :c, :s, 'student', NOW())"),
            {"id": student_id, "n": name, "c": s_class, "s": s_section})
        db.session.commit()
        os.makedirs(os.path.join(DATASET_DIR, student_id), exist_ok=True)
        return jsonify({"status": "success", "student_id": student_id})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/admin/train_trigger", methods=["POST"])
def admin_train_trigger():
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 401
    threading.Thread(target=train_model_background, args=(DATASET_DIR, lambda p, m: write_train_status({"running":True,"progress":p,"message":m})), daemon=True).start()
    return jsonify({"status": "started"})

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == "admin123":
            session['admin_logged_in'] = True
            return redirect(url_for('admin_directory'))
    return render_template("login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route("/mark_attendance")
def mark_attendance():
    return render_template("mark_attendance.html")

@app.route("/attendance_record")
def attendance_record():
    records = db.session.execute(text("""
        SELECT a.timestamp, u.name, u.class, u.section 
        FROM attendance a 
        JOIN users u ON a.student_id = u.user_id 
        ORDER BY a.timestamp DESC LIMIT 50
    """)).fetchall()
    return render_template("attendance_record.html", records=records)

@app.route("/admin/view_student/<student_id>")
def admin_view_student(student_id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    student = db.session.execute(text("SELECT * FROM users WHERE user_id = :id"), {"id": student_id}).fetchone()
    attendance = db.session.execute(text("SELECT timestamp FROM attendance WHERE student_id = :id ORDER BY timestamp DESC"), {"id": student_id}).fetchall()
    return render_template("view_student.html", student=student, attendance=attendance)

# Change the function name to match what url_for expects
@app.route("/admin/delete/<student_id>", methods=["POST"])
def delete_student(student_id): # Ensure this name matches the HTML url_for
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

# Also ensure this view route exists for the 'View' button in the directory
@app.route("/admin/view_student/<student_id>")
def admin_view_student(student_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    res = db.session.execute(text("SELECT name FROM users WHERE user_id = :sid"), {"sid": student_id}).fetchone()
    if not res:
        return redirect(url_for('admin_directory'))

    folder_path = os.path.join(DATASET_DIR, student_id)
    images = [f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.png'))] if os.path.exists(folder_path) else []
    return render_template("admin_view.html", student_id=student_id, student_name=res[0], images=sorted(images))

# Add this to app.py to stop the 404 when clicking 'Train'
@app.route("/train_model", methods=["POST"])
def train_model_api():
    # This matches the JS call that was 404-ing
    return train_model_route()

@app.route("/admin/directory")
def admin_directory():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    students = db.session.execute(text("SELECT user_id, name, class, section FROM users WHERE role = 'student'")).fetchall()
    return render_template("admin_directory.html", students=students)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)