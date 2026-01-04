# =========================================================
# run_pi.py
# Digital Attendance System – Pi 5 High-Stability Version
# Integrated with Admin Dashboard for Dataset Viewing
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

running = True

# =========================================================
# NEW: ADMIN & DASHBOARD ROUTES
# =========================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Simple login gate for the admin panel"""
    if request.method == 'POST':
        # Change 'admin123' to your preferred password
        if request.form.get('password') == 'admin123':
            # Redirecting specifically to your folder for now
            return redirect(url_for('admin_view', student_name='Abhisam_Sharma'))
        else:
            return "Invalid Password. <a href='/admin/login'>Try again</a>"
    
    return '''
        <div style="text-align:center; margin-top:100px; font-family:sans-serif;">
            <h2>Admin Dataset Access</h2>
            <form method="post">
                <input type="password" name="password" placeholder="Password" style="padding:10px;">
                <button type="submit" style="padding:10px;">Login</button>
            </form>
        </div>
    '''

@app.route('/admin/view/<student_name>')
def admin_view(student_name):
    """Scans the dataset folder and renders the images in a grid"""
    dataset_path = os.path.join('dataset', student_name)
    
    if not os.path.exists(dataset_path):
        return f"Folder for {student_name} not found in dataset/", 404

    # Get list of all .jpg files in the student's folder
    images = [f for f in os.listdir(dataset_path) if f.endswith('.jpg')]
    
    # Ensure the symlink exists so Flask can serve these external images
    # We use 'dataset_link' as created in our previous terminal step
    link_path = os.path.join('static', 'dataset_link')
    if not os.path.exists(link_path):
        try:
            os.symlink(os.path.abspath('dataset'), link_path)
            print("[SYSTEM] Created missing symlink for dataset.")
        except Exception as e:
            print(f"[ERROR] Could not create symlink: {e}")

    return render_template('admin_view.html', student_name=student_name, images=images)

# =========================================================
# PI 5 PERSISTENT CAPTURE LOGIC
# =========================================================

def get_single_frame():
    """Grabs a single YUV frame via rpicam-vid for maximum stability on Pi 5"""
    cmd = [
        "rpicam-vid", "--noproview", "--camera", "0",
        "--width", "640", "--height", "480",
        "--frames", "1", "--timeout", "200",
        "--codec", "yuv420", "-o", "-"
    ]
    try:
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3)
        if not process.stdout or len(process.stdout) == 0:
            return None

        expected_size = int(640 * 480 * 1.5)
        raw_data = process.stdout[:expected_size]
        
        if len(raw_data) < expected_size:
            return None

        yuv_array = np.frombuffer(raw_data, dtype=np.uint8).reshape((int(480 * 1.5), 640))
        bgr_frame = cv2.cvtColor(yuv_array, cv2.COLOR_YUV2BGR_I420)
        return bgr_frame
    except Exception as e:
        print(f"[CAMERA ERROR] Stream failed: {e}")
        return None

# =========================================================
# MAIN RECOGNITION LOOP
# =========================================================

def camera_loop():
    system_message("System Ready", "Scanning faces")
    print("[PI 5] Camera System Online (High-Stability Mode)")

    mp_face = mp.solutions.face_detection.FaceDetection(
        model_selection=0, min_detection_confidence=0.6
    )

    clf = load_model_if_exists()
    if clf is None:
        print("[WARNING] No trained model found. Use the Admin Panel to check dataset.")

    while running:
        frame = get_single_frame()
        if frame is None:
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

                    if confidence > 0.5:
                        with app.app_context():
                            today = datetime.now().date()
                            try:
                                exists = db.session.execute(
                                    text("SELECT 1 FROM attendance WHERE student_id = :sid AND DATE(timestamp) = :today"),
                                    {"sid": user_id, "today": today}
                                ).fetchone()

                                name = db.session.execute(
                                    text("SELECT name FROM users WHERE user_id = :sid"),
                                    {"sid": user_id}
                                ).scalar() or user_id

                                if not exists:
                                    db.session.execute(
                                        text("INSERT INTO attendance (student_id, class_id, timestamp, status) VALUES (:sid, 1, NOW(), 'present')"),
                                        {"sid": user_id}
                                    )
                                    db.session.commit()
                                    attendance_success(name, confidence)
                                else:
                                    attendance_duplicate(name)
                            except Exception as db_err:
                                print(f"[DB ERROR] {db_err}")
                    else:
                        attendance_unknown()

                time.sleep(2) # Cooldown

# =========================================================
# SHUTDOWN & STARTUP
# =========================================================

def shutdown_handler(signum, frame):
    global running
    print("\n[SHUTDOWN] Closing system...")
    running = False
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

if __name__ == "__main__":
    # Clean up any stuck processes before starting
    subprocess.run(["sudo", "pkill", "-9", "rpicam-still"], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "pkill", "-9", "rpicam-vid"], stderr=subprocess.DEVNULL)
    
    print("[START] Digital Attendance System Initializing...")
    camera_thread = threading.Thread(target=camera_loop, daemon=True)
    camera_thread.start()

    # host="0.0.0.0" allows access from your laptop browser
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)