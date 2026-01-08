# =========================================================
# run_pi.py - PRODUCTION VERSION (Fixed & Polished)
# Digital Attendance System – Pi 5 High-Stability
# Handles: MJPEG Streaming, State Management, AI Recognition
# =========================================================

import threading
import time
import signal
import sys
import subprocess
import os
from datetime import datetime

# Flask and Web helpers
from flask import render_template, request, redirect, url_for, Response, jsonify
from sqlalchemy import text
from app import app, db  # Inherits all routes from app.py

# Computer Vision & AI libraries
import cv2
import mediapipe as mp
import numpy as np

# Hardware helpers (LCD, Buzzer, LEDs)
from hardware import (
    attendance_success,
    attendance_duplicate,
    attendance_unknown,
    system_message,
    cleanup
)

# AI Model helpers (Face Embeddings & Prediction)
from model import (
    load_model_if_exists,
    predict_with_model,
    crop_face_and_embed
)

# =========================================================
# GLOBAL STATE MANAGEMENT
# =========================================================
running = True                # Main loop control flag
latest_frame = None           # Buffer for MJPEG stream
system_state = "IDLE"         # Current state: IDLE, ALIGNING, SCANNING
last_recognition_result = {}  # Stores the most recent scan result for browser polling
state_lock = threading.Lock() # Thread-safe state transitions

def log_event(status, message):
    """Clean terminal logger with timestamps."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {status.upper():10} | {message}")

# =========================================================
# WEB ROUTES: VIDEO STREAMING
# =========================================================

def generate_frames():
    """Generator function for MJPEG stream."""
    global latest_frame
    while running:
        if latest_frame is not None:
            ret, buffer = cv2.imencode('.jpg', latest_frame)
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.05)  # ~20 FPS

@app.route('/video_feed')
def video_feed():
    """Serves the live Pi camera feed to <img> tags in HTML."""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# =========================================================
# WEB ROUTES: ATTENDANCE MARKING (Hardware Trigger)
# =========================================================

@app.route('/trigger_attendance')
def trigger_attendance():
    """Initiates 10-second alignment phase before AI scanning."""
    global system_state, last_recognition_result
    
    with state_lock:
        if system_state != "IDLE":
            return jsonify({"status": "busy", "message": "System currently processing"}), 400
        
        system_state = "ALIGNING"
        last_recognition_result = {}  
        
        log_event("SYSTEM", "Attendance triggered. Starting 10s alignment.")
        threading.Timer(10.0, set_scanning_state).start()
        
        return jsonify({"status": "aligning", "seconds": 10})

def set_scanning_state():
    global system_state
    with state_lock:
        system_state = "SCANNING"
        log_event("SYSTEM", "Executing AI scan...")

@app.route('/get_scan_result')
def get_scan_result():
    """Polling endpoint for the browser to check scan results."""
    global last_recognition_result
    return jsonify(last_recognition_result)

# =========================================================
# WEB ROUTES: STUDENT ENROLLMENT (Pi-Specific Logic)
# =========================================================

# Updated Route in run_pi.py
@app.route('/add_student_pi', methods=['POST'])
def add_student_from_pi():
    try:
        # 1. Capture form data from request
        name = request.form.get('name')
        roll = request.form.get('roll')
        reg_no = request.form.get('reg_no')
        class_name = request.form.get('class')
        section = request.form.get('sec')
        
        # 2. Generate a Unique ID (Matches app.py logic)
        # Result example: S1706240000000
        student_id = f"S{int(time.time() * 1000)}" 

        with app.app_context():
            # 3. Securely insert into database
            # Ensure your user_id column in MySQL is VARCHAR(50)
            db.session.execute(
                text("""
                    INSERT INTO users (user_id, name, roll, reg_no, class, section, role) 
                    VALUES (:id, :name, :roll, :reg_no, :class, :sec, 'student')
                """),
                {
                    "id": student_id, 
                    "name": name, 
                    "roll": roll, 
                    "reg_no": reg_no, 
                    "class": class_name, 
                    "sec": section
                }
            )
            db.session.commit()
            
            # 4. Create the folder where 50 images will be stored
            os.makedirs(os.path.join('dataset', student_id), exist_ok=True)
            
            log_event("ENROLL", f"Success: {name} (ID: {student_id})")
            return jsonify({"status": "success", "student_id": student_id})

    except Exception as e:
        # Catch errors like duplicate roll numbers or DB disconnection
        log_event("ERROR", f"Enrollment Failed: {str(e)}")
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/trigger_capture')
def trigger_capture():
    """Starts the 50-image capture sequence."""
    global system_state
    student_id = request.args.get('student_id')
    
    if not student_id:
        return jsonify({"error": "No student_id provided"}), 400

    def capture_sequence(sid):
        global system_state, latest_frame
        with state_lock:
            system_state = "ALIGNING"
        
        log_event("ENROLL", "Alignment phase (10s)...")
        time.sleep(10)
        
        dataset_path = os.path.join('dataset', sid)
        os.makedirs(dataset_path, exist_ok=True)
        
        log_event("ENROLL", f"Capturing 50 images for ID: {sid}")
        
        captured_count = 0
        # Increased range to ensure we get 50 good ones
        for i in range(100): 
            if captured_count >= 50:
                break
                
            # Use the global buffer instead of re-opening the camera
            if latest_frame is not None:
                frame_to_save = latest_frame.copy()
                cv2.imwrite(os.path.join(dataset_path, f"img_{captured_count}.jpg"), frame_to_save)
                captured_count += 1
                # Small delay to allow user to move slightly for different angles
                time.sleep(0.2) 
        
        log_event("ENROLL", f"Capture complete: {captured_count}/50 saved")
        with state_lock:
            system_state = "IDLE"

    threading.Thread(target=capture_sequence, args=(student_id,), daemon=True).start()
    return jsonify({"status": "capturing"})

# =========================================================
# CAMERA INTERFACE: Pi 5 High-Stability Logic
# =========================================================

def get_single_frame():
    """Captures a single frame via libcamera to prevent Pi 5 locking."""
    cmd = [
        "rpicam-vid", "--nopreview", "--camera", "0",
        "--width", "640", "--height", "480",
        "--frames", "1", "--timeout", "200",
        "--codec", "yuv420", "-o", "-"
    ]
    try:
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4)
        if not process.stdout: return None

        expected_size = int(640 * 480 * 1.5)
        raw_data = process.stdout[:expected_size]
        yuv_array = np.frombuffer(raw_data, dtype=np.uint8).reshape((int(480 * 1.5), 640))
        return cv2.cvtColor(yuv_array, cv2.COLOR_YUV2BGR_I420)
    except:
        return None

# =========================================================
# MAIN RECOGNITION LOOP
# =========================================================

def camera_loop():
    global latest_frame, system_state, last_recognition_result
    
    system_message("System Online", "Ready to Scan")
    mp_face = mp.solutions.face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.4)
    clf = load_model_if_exists()
    
    if clf is None:
        log_event("WARNING", "Model not found. Recognition disabled.")

    while running:
        frame = get_single_frame()
        if frame is None:
            subprocess.run(["sudo", "pkill", "-9", "rpicam-vid"], stderr=subprocess.DEVNULL)
            continue

        latest_frame = frame.copy()

        if system_state == "SCANNING":
            perform_recognition(frame, mp_face, clf)
            with state_lock:
                system_state = "IDLE"

def perform_recognition(frame, mp_face, clf):
    global last_recognition_result
    if clf is None:
        attendance_unknown()
        return

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = mp_face.process(rgb_frame)

    if not results.detections:
        last_recognition_result = {"status": "failure", "message": "No face detected"}
        attendance_unknown()
        return

    embedding = crop_face_and_embed(frame, results.detections[0])
    if embedding is None:
        attendance_unknown()
        return

    user_id, confidence = predict_with_model(clf, embedding)
    
    if confidence > 0.35:
        process_attendance(user_id, confidence)
    else:
        last_recognition_result = {"status": "failure", "message": "Low confidence"}
        attendance_unknown()

def process_attendance(user_id, confidence):
    global last_recognition_result
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
            ).scalar() or f"ID-{user_id}"

            if not exists:
                db.session.execute(
                    text("INSERT INTO attendance (student_id, class_id, timestamp, status) VALUES (:sid, 1, NOW(), 'present')"),
                    {"sid": user_id}
                )
                db.session.commit()
                last_recognition_result = {"status": "success", "name": name, "confidence": round(confidence, 2)}
                attendance_success(name, confidence)
            else:
                last_recognition_result = {"status": "duplicate", "name": name}
                attendance_duplicate(name)
        except Exception as e:
            log_event("DB ERROR", str(e))

# =========================================================
# SYSTEM LIFECYCLE
# =========================================================

def shutdown_handler(signum, frame):
    global running
    running = False
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

if __name__ == "__main__":
    subprocess.run(["sudo", "pkill", "-9", "rpicam-vid"], stderr=subprocess.DEVNULL)
    threading.Thread(target=camera_loop, daemon=True).start()
    log_event("WEB", "Flask server starting on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)