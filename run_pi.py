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
from app import app, db

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
    """
    Clean terminal logger with timestamps.
    Prevents text flooding by limiting output to meaningful events.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {status.upper():10} | {message}")

# =========================================================
# WEB ROUTES: VIDEO STREAMING
# =========================================================

def generate_frames():
    """
    Generator function for MJPEG stream.
    Continuously yields JPEG frames to the browser.
    Runs at ~20 FPS to balance quality and network bandwidth.
    """
    global latest_frame
    while running:
        if latest_frame is not None:
            # Encode the current frame as JPEG
            ret, buffer = cv2.imencode('.jpg', latest_frame)
            if ret:
                frame_bytes = buffer.tobytes()
                # Yield in MJPEG format (multipart HTTP response)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.05)  # ~20 FPS

@app.route('/video_feed')
def video_feed():
    """
    Route that serves the live Pi camera feed to <img> tags in HTML.
    Uses multipart/x-mixed-replace for continuous frame streaming.
    """
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# =========================================================
# NEW PAGE NAVIGATION ROUTES (PASTE HERE)
# =========================================================

@app.route('/')
def index():
    """Renders the main dashboard (index.html)"""
    return render_template('index.html')

@app.route('/enrollment')
def add_student_page():
    """Renders the enrollment form (add_student.html)"""
    return render_template('add_student.html')

@app.route('/mark_attendance')
def mark_attendance_page():
    """Renders the scanning page (mark_attendance.html)"""
    return render_template('mark_attendance.html')

@app.route('/attendance_record')
def attendance_record_page():
    """Renders the records/history page"""
    return render_template('attendance_record.html')

@app.route('/admin/login')
def admin_login():
    """Renders the admin view page"""
    return render_template('admin_view.html')


# =========================================================
# WEB ROUTES: ATTENDANCE MARKING
# =========================================================

@app.route('/trigger_attendance')
def trigger_attendance():
    """
    Triggered by 'Start' button on mark_attendance.html.
    Initiates 10-second alignment phase before AI scanning.
    
    Returns:
        JSON with status and countdown duration
    """
    global system_state, last_recognition_result
    
    with state_lock:
        if system_state != "IDLE":
            return jsonify({"status": "busy", "message": "System currently processing"}), 400
        
        # Transition to ALIGNING state
        system_state = "ALIGNING"
        last_recognition_result = {}  # Clear previous result
        
        log_event("SYSTEM", "Attendance triggered. Starting 10s alignment phase.")
        
        # Schedule transition to SCANNING after 10 seconds
        threading.Timer(10.0, set_scanning_state).start()
        
        return jsonify({"status": "aligning", "seconds": 10})

def set_scanning_state():
    """
    Internal callback to transition from ALIGNING to SCANNING.
    Called automatically after the 10-second countdown.
    """
    global system_state
    with state_lock:
        system_state = "SCANNING"
        log_event("SYSTEM", "Alignment complete. Executing AI scan...")

@app.route('/get_scan_result')
def get_scan_result():
    """
    Polling endpoint for the browser to check scan results.
    Returns the most recent recognition result.
    
    Returns:
        JSON with recognition status, name, confidence, and message
    """
    global last_recognition_result
    return jsonify(last_recognition_result)

# =========================================================
# WEB ROUTES: STUDENT ENROLLMENT
# =========================================================

@app.route('/add_student', methods=['POST'])
def add_student():
    """
    Saves new student information to the database.
    Called by camera_add_student.js before image capture begins.
    
    Form Data:
        name, roll, reg_no, class, sec
    
    Returns:
        JSON with the newly created student_id
    """
    try:
        name = request.form.get('name')
        roll = request.form.get('roll')
        reg_no = request.form.get('reg_no')
        class_name = request.form.get('class')
        section = request.form.get('sec')
        
        with app.app_context():
            # Insert student into users table
            result = db.session.execute(
                text("""
                    INSERT INTO users (name, roll, reg_no, class, section) 
                    VALUES (:name, :roll, :reg_no, :class, :sec)
                """),
                {
                    "name": name,
                    "roll": roll,
                    "reg_no": reg_no,
                    "class": class_name,
                    "sec": section
                }
            )
            db.session.commit()
            
            # Retrieve the auto-generated student_id
            student_id = result.lastrowid
            
            log_event("ENROLL", f"New student registered: {name} (ID: {student_id})")
            
            return jsonify({
                "status": "success",
                "student_id": str(student_id),
                "message": "Student information saved"
            })
            
    except Exception as e:
        log_event("ERROR", f"Failed to add student: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/trigger_capture')
def trigger_capture():
    """
    Initiates the image capture sequence for student enrollment.
    Captures 50 images after a 10-second alignment phase.
    
    Query Parameters:
        student_id: The ID of the student being enrolled
    
    Returns:
        JSON with capture status
    """
    global system_state
    student_id = request.args.get('student_id')
    
    if not student_id:
        return jsonify({"error": "No student_id provided"}), 400

    def capture_sequence(sid):
        """
        Background thread that handles the capture process.
        Phase 1: 10-second alignment
        Phase 2: Capture 50 frames with slight delays for variety
        """
        global system_state
        
        # Phase 1: Alignment
        with state_lock:
            system_state = "ALIGNING"
        
        log_event("ENROLL", f"Alignment phase started for ID: {sid}")
        time.sleep(10)
        
        # Phase 2: Capture
        dataset_path = os.path.join('dataset', sid)
        os.makedirs(dataset_path, exist_ok=True)
        
        log_event("ENROLL", f"Capturing 50 training images for ID: {sid}")
        
        captured_count = 0
        for i in range(50):
            frame = get_single_frame()
            if frame is not None:
                cv2.imwrite(os.path.join(dataset_path, f"img_{i}.jpg"), frame)
                captured_count += 1
            time.sleep(0.05)  # Small delay for natural variation
        
        log_event("ENROLL", f"Capture complete: {captured_count}/50 images saved")
        
        # Return to IDLE state
        with state_lock:
            system_state = "IDLE"

    # Start capture in background thread
    threading.Thread(target=capture_sequence, args=(student_id,), daemon=True).start()
    
    return jsonify({"status": "capturing", "message": "Capture sequence initiated"})

# =========================================================
# CAMERA INTERFACE: Pi 5 High-Stability Logic
# =========================================================

def get_single_frame():
    """
    Captures a single frame using rpicam-vid instead of OpenCV.
    This bypasses camera locking issues on Pi 5.
    
    Returns:
        numpy.ndarray: BGR image frame, or None if capture failed
    """
    cmd = [
        "rpicam-vid", "--nopreview", "--camera", "0",
        "--width", "640", "--height", "480",
        "--frames", "1", "--timeout", "200",
        "--codec", "yuv420", "-o", "-"
    ]
    
    try:
        process = subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.DEVNULL, 
            timeout=4
        )
        
        if not process.stdout:
            return None

        # Calculate expected size for 640x480 YUV420 (1.5 bytes per pixel)
        expected_size = int(640 * 480 * 1.5)
        raw_data = process.stdout[:expected_size]
        
        # Reshape and convert YUV to BGR
        yuv_array = np.frombuffer(raw_data, dtype=np.uint8).reshape((int(480 * 1.5), 640))
        bgr_frame = cv2.cvtColor(yuv_array, cv2.COLOR_YUV2BGR_I420)
        
        return bgr_frame
        
    except Exception as e:
        # Silently fail to avoid log flooding
        return None

# =========================================================
# MAIN RECOGNITION LOOP
# =========================================================

def camera_loop():
    """
    Main camera thread that runs continuously.
    
    Behavior:
    - Always captures frames for the MJPEG stream
    - Only performs AI recognition when state == SCANNING
    - Updates global result dictionary for browser polling
    """
    global latest_frame, system_state, last_recognition_result
    
    # Initialize hardware and AI components
    system_message("System Online", "Ready to Scan")
    
    mp_face = mp.solutions.face_detection.FaceDetection(
        model_selection=0,  # Short-range model (0-2 meters)
        min_detection_confidence=0.4
    )
    
    clf = load_model_if_exists()
    
    if clf is None:
        log_event("WARNING", "No trained model found. Recognition disabled.")

    while running:
        # Capture frame
        frame = get_single_frame()
        
        if frame is None:
            # Clean up stalled camera processes
            subprocess.run(["sudo", "pkill", "-9", "rpicam-vid"], stderr=subprocess.DEVNULL)
            continue

        # Update stream buffer
        latest_frame = frame.copy()

        # Only perform AI recognition when in SCANNING state
        if system_state == "SCANNING":
            perform_recognition(frame, mp_face, clf)
            
            # Return to IDLE after processing
            with state_lock:
                system_state = "IDLE"

def perform_recognition(frame, mp_face, clf):
    """
    Executes the AI recognition pipeline on a single frame.
    
    Steps:
    1. Detect faces using MediaPipe
    2. Extract 128D embeddings
    3. Predict identity using RandomForest
    4. Log to database and trigger hardware
    5. Update result dictionary for browser
    
    Args:
        frame: BGR image from camera
        mp_face: MediaPipe face detection model
        clf: Trained RandomForest classifier
    """
    global last_recognition_result
    
    if clf is None:
        log_event("ERROR", "Cannot recognize: Model not loaded")
        last_recognition_result = {
            "status": "error",
            "message": "Model not trained yet"
        }
        attendance_unknown()
        return

    # Convert to RGB for MediaPipe
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = mp_face.process(rgb_frame)

    if not results.detections:
        log_event("FAILURE", "No face detected in scan window")
        last_recognition_result = {
            "status": "failure",
            "message": "No face detected"
        }
        attendance_unknown()
        return

    # Process first detected face
    detection = results.detections[0]
    embedding = crop_face_and_embed(frame, detection)
    
    if embedding is None:
        log_event("FAILURE", "Could not extract face embedding")
        last_recognition_result = {
            "status": "failure",
            "message": "Face extraction failed"
        }
        attendance_unknown()
        return

    # Predict identity
    user_id, confidence = predict_with_model(clf, embedding)
    
    if confidence > 0.35:  # Threshold tuned for RandomForest
        process_attendance(user_id, confidence)
    else:
        log_event("FAILURE", f"Low confidence: {confidence:.2f}")
        last_recognition_result = {
            "status": "failure",
            "message": f"Face not recognized (Confidence: {confidence:.2f})"
        }
        attendance_unknown()

def process_attendance(user_id, confidence):
    """
    Logs attendance to database and triggers hardware feedback.
    
    Business Logic:
    - Checks for duplicate attendance on the same day
    - Logs new attendance records with timestamp
    - Triggers appropriate hardware signals (buzzer, LCD, LEDs)
    - Updates result dictionary for browser feedback
    
    Args:
        user_id: Predicted student ID
        confidence: Recognition confidence score (0-1)
    """
    global last_recognition_result
    
    with app.app_context():
        today = datetime.now().date()
        
        try:
            # Check for duplicate attendance
            exists = db.session.execute(
                text("""
                    SELECT 1 FROM attendance 
                    WHERE student_id = :sid AND DATE(timestamp) = :today
                """),
                {"sid": user_id, "today": today}
            ).fetchone()

            # Fetch student name
            name = db.session.execute(
                text("SELECT name FROM users WHERE user_id = :sid"),
                {"sid": user_id}
            ).scalar() or f"ID-{user_id}"

            if not exists:
                # Log new attendance
                db.session.execute(
                    text("""
                        INSERT INTO attendance (student_id, class_id, timestamp, status) 
                        VALUES (:sid, 1, NOW(), 'present')
                    """),
                    {"sid": user_id}
                )
                db.session.commit()
                
                log_event("SUCCESS", f"LOGGED: {name} (Confidence: {confidence:.2f})")
                
                # Update result for browser
                last_recognition_result = {
                    "status": "success",
                    "name": name,
                    "student_id": user_id,
                    "confidence": round(confidence, 2),
                    "message": "Attendance marked successfully"
                }
                
                # Trigger hardware success signal
                attendance_success(name, confidence)
                
            else:
                log_event("DUPLICATE", f"ALREADY MARKED: {name}")
                
                last_recognition_result = {
                    "status": "duplicate",
                    "name": name,
                    "student_id": user_id,
                    "confidence": round(confidence, 2),
                    "message": "Already marked today"
                }
                
                attendance_duplicate(name)
                
        except Exception as e:
            log_event("DB ERROR", str(e))
            last_recognition_result = {
                "status": "error",
                "message": "Database error occurred"
            }

# =========================================================
# SYSTEM LIFECYCLE MANAGEMENT
# =========================================================

def shutdown_handler(signum, frame):
    """
    Graceful shutdown handler for SIGINT (Ctrl+C) and SIGTERM.
    Cleans up GPIO pins and camera processes.
    """
    global running
    log_event("SYSTEM", "Shutting down...")
    running = False
    cleanup()
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# =========================================================
# APPLICATION ENTRY POINT
# =========================================================

if __name__ == "__main__":
    # Clean up any leftover camera processes from previous runs
    subprocess.run(["sudo", "pkill", "-9", "rpicam-vid"], stderr=subprocess.DEVNULL)
    
    # Start the camera/AI thread
    threading.Thread(target=camera_loop, daemon=True).start()

    log_event("WEB", "Flask server starting on http://0.0.0.0:5000")
    
    # Run Flask server
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)