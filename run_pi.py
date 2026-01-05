# =========================================================
# run_pi.py
# Digital Attendance System – Pi 5 High-Stability Version
# Finalized Version with Dynamic Admin Selection
# =========================================================

import threading
import time
import signal
import sys
import subprocess
import os
from datetime import datetime

# Flask and Web helpers
from flask import render_template, request, redirect, url_for, Response
from sqlalchemy import text
from app import app, db

# Computer Vision & AI libraries
import cv2
import mediapipe as mp
import numpy as np

# Hardware helpers
from hardware import (
    attendance_success,
    attendance_duplicate,
    attendance_unknown,
    system_message,
    cleanup
)

# AI Model helpers
from model import (
    load_model_if_exists,
    predict_with_model,
    crop_face_and_embed
)

# Global flag for thread management
running = True

# =========================================================
# ADMIN & DATASET MANAGEMENT ROUTES
# =========================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Gatekeeper for the Admin Panel"""
    if request.method == 'POST':
        # Security: Simple password check
        if request.form.get('password') == 'admin123':
            return redirect(url_for('admin_dashboard'))
        else:
            return "Invalid Password. <a href='/admin/login'>Try again</a>"
    
    return '''
        <div style="text-align:center; margin-top:100px; font-family:sans-serif; background:#f4f7f6; height:100vh; padding-top:50px;">
            <div style="display:inline-block; background:white; padding:40px; border-radius:15px; shadow: 0 4px 10px rgba(0,0,0,0.1);">
                <h2 style="color:#0f172a;">Admin Access</h2>
                <form method="post">
                    <input type="password" name="password" placeholder="Enter Password" style="padding:12px; width:200px; border-radius:5px; border:1px solid #ddd;"><br><br>
                    <button type="submit" style="padding:10px 30px; background:#3b82f6; color:white; border:none; border-radius:5px; cursor:pointer;">Login</button>
                </form>
                <br><a href="/" style="color:#666; text-decoration:none;">Return to Dashboard</a>
            </div>
        </div>
    '''

@app.route('/admin/dashboard')
def admin_dashboard():
    """Automatically lists all students found in the dataset folder"""
    if not os.path.exists('dataset'):
        return "Dataset folder missing.", 404
    
    # Get all subfolders in 'dataset'
    students = [d for d in os.listdir('dataset') if os.path.isdir(os.path.join('dataset', d))]
    
    # Create a simple list of links (or you can create a dedicated admin_list.html template)
    links = "".join([f'''
        <div style="padding:15px; border-bottom:1px solid #eee;">
            <a href="/admin/view/{s}" style="text-decoration:none; color:#3b82f6; font-weight:bold; font-size:18px;">📂 {s}</a>
        </div>
    ''' for s in students])

    return f'''
        <div style="font-family:sans-serif; max-width:600px; margin:50px auto; background:white; padding:30px; border-radius:12px; box-shadow:0 10px 25px rgba(0,0,0,0.1);">
            <h2 style="border-bottom:2px solid #3b82f6; padding-bottom:10px;">Select Student Dataset</h2>
            {links if students else "<p>No datasets found.</p>"}
            <br><a href="/" style="color:#666;">← Back to Main Dashboard</a>
        </div>
    '''

@app.route('/admin/view/<student_name>')
def admin_view(student_name):
    """Renders images for a specific student using the fixed symlink path"""
    dataset_path = os.path.join('dataset', student_name)
    
    if not os.path.exists(dataset_path):
        return f"Folder for {student_name} not found.", 404

    # Fetch all jpg images
    images = [f for f in os.listdir(dataset_path) if f.lower().endswith('.jpg')]
    
    # SYSTEM SYMLINK CHECK: Ensures static/dataset_link points to the root dataset folder
    link_path = os.path.join('static', 'dataset_link')
    if not os.path.exists(link_path):
        try:
            os.symlink(os.path.abspath('dataset'), link_path)
            print("[SYSTEM] Created dataset_link symlink.")
        except Exception as e:
            print(f"[ERROR] Symlink creation failed: {e}")

    return render_template('admin_view.html', student_name=student_name, images=images)

# =========================================================
# PI 5 HIGH-STABILITY CAMERA LOGIC
# =========================================================

def get_single_frame():
    """Directly calls rpicam-vid for YUV bytes to bypass OpenCV/Libcamera hangs"""
    cmd = [
        "rpicam-vid", "--noproview", "--camera", "0",
        "--width", "640", "--height", "480",
        "--frames", "1", "--timeout", "250",
        "--codec", "yuv420", "-o", "-"
    ]
    try:
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4)
        if not process.stdout or len(process.stdout) == 0:
            return None

        expected_size = int(640 * 480 * 1.5)
        raw_data = process.stdout[:expected_size]
        
        if len(raw_data) < expected_size:
            return None

        # Convert YUV420 to BGR for OpenCV processing
        yuv_array = np.frombuffer(raw_data, dtype=np.uint8).reshape((int(480 * 1.5), 640))
        bgr_frame = cv2.cvtColor(yuv_array, cv2.COLOR_YUV2BGR_I420)
        return bgr_frame
    except Exception as e:
        print(f"[CAMERA ERROR] Device busy or timed out: {e}")
        return None

# =========================================================
# MAIN RECOGNITION THREAD
# =========================================================

def camera_loop():
    """Background thread for real-time face scanning"""
    system_message("System Online", "Ready to Scan")
    print("[START] Recognition thread active.")

    mp_face = mp.solutions.face_detection.FaceDetection(
        model_selection=0, min_detection_confidence=0.4
    )

    clf = load_model_if_exists()
    if clf is None:
        print("[WARNING] No model.pkl found. Training required.")

    while running:
        frame = get_single_frame()
        if frame is None:
            # If camera hangs, force kill any zombie processes
            subprocess.run(["sudo", "pkill", "-9", "rpicam-vid"], stderr=subprocess.DEVNULL)
            time.sleep(1)
            continue

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = mp_face.process(rgb_frame)

        if results.detections:
            for detection in results.detections:
                emb = crop_face_and_embed(frame, detection)

                if emb is not None and clf is not None:
                    user_id, confidence = predict_with_model(clf, emb)
                    print(f"[DEBUG] Detected: {user_id} | Confidence: {confidence:.2f}")

                    # Confidence Threshold: 0.5 (Adjust based on lighting)
                    if confidence > 0.35:
                        with app.app_context():
                            today = datetime.now().date()
                            try:
                                # 1. Check if already marked
                                exists = db.session.execute(
                                    text("SELECT 1 FROM attendance WHERE student_id = :sid AND DATE(timestamp) = :today"),
                                    {"sid": user_id, "today": today}
                                ).fetchone()

                                # 2. Get user's real name
                                name = db.session.execute(
                                    text("SELECT name FROM users WHERE user_id = :sid"),
                                    {"sid": user_id}
                                ).scalar() or user_id

                                if not exists:
                                    # 3. Log attendance (Defaulting to class_id 1)
                                    db.session.execute(
                                        text("INSERT INTO attendance (student_id, class_id, timestamp, status) VALUES (:sid, 1, NOW(), 'present')"),
                                        {"sid": user_id}
                                    )
                                    db.session.commit()
                                    attendance_success(name, confidence)
                                else:
                                    attendance_duplicate(name)
                                    
                            except Exception as db_err:
                                print(f"[DB ERROR] Constraint failure or missing class: {db_err}")
                    else:
                        attendance_unknown()

                # Cooldown to prevent spamming the buzzer/DB
                time.sleep(2) 

# =========================================================
# LIFECYCLE MANAGEMENT
# =========================================================

def shutdown_handler(signum, frame):
    """Gracefully closes GPIO and stops threads"""
    global running
    print("\n[SHUTDOWN] Cleaning up hardware and stopping server...")
    running = False
    cleanup() # From hardware.py
    sys.exit(0)

# Register signals for CTRL+C or Systemd Stop
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

if __name__ == "__main__":
    # Pre-startup cleanup of camera locks
    subprocess.run(["sudo", "pkill", "-9", "rpicam-still"], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "pkill", "-9", "rpicam-vid"], stderr=subprocess.DEVNULL)
    
    # Start AI Recognition in background
    camera_thread = threading.Thread(target=camera_loop, daemon=True)
    camera_thread.start()

    # Launch Web Dashboard
    print("[WEB] Dashboard available at http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)