# =========================================================
# run_pi.py
# Digital Attendance System – Raspberry Pi Camera Version
# Uses Picamera2 (libcamera) instead of OpenCV VideoCapture
# =========================================================

# ------------------------------
# Standard Python libraries
# ------------------------------
import threading           # Run camera loop in background
import time                # Delay handling
import signal              # Capture Ctrl+C / shutdown signals
import sys                 # System exit handling
from datetime import datetime

# ------------------------------
# Computer Vision & AI libraries
# ------------------------------
import cv2                 # OpenCV (for image processing, NOT camera)
import mediapipe as mp     # Face detection AI
import numpy as np         # Numerical operations (required by Picamera2)

# ------------------------------
# Raspberry Pi Camera (libcamera)
# ------------------------------
from picamera2 import Picamera2

# ------------------------------
# Database & Flask
# ------------------------------
from sqlalchemy import text
from app import app, db

# ------------------------------
# Hardware & UI helpers
# ------------------------------
from hardware import (
    attendance_success,     # LCD + buzzer success
    attendance_duplicate,   # Already marked today
    attendance_unknown,     # Unknown face
    system_message,         # LCD system message
    cleanup                 # GPIO cleanup
)

# ------------------------------
# AI Model helpers
# ------------------------------
from model import (
    load_model_if_exists,   # Loads trained face model
    predict_with_model,     # Predicts identity
    crop_face_and_embed     # Converts face → embedding
)

# =========================================================
# GLOBAL CONTROL FLAG
# =========================================================
running = True   # Used to safely stop camera thread

# =========================================================
# CAMERA & FACE RECOGNITION LOOP (Pi Camera Version)
# =========================================================
def camera_loop():
    """
    Background thread that:
    1. Captures frames from Raspberry Pi Camera using libcamera
    2. Detects faces using MediaPipe
    3. Converts faces to embeddings
    4. Recognizes users and marks attendance in database
    """

    # Show startup message on LCD
    system_message("System Ready", "Scanning faces")

    # -----------------------------------------------------
    # Initialize Raspberry Pi Camera (Picamera2)
    # -----------------------------------------------------
    picam2 = Picamera2()

    # Camera configuration:
    # - RGB888 format (MediaPipe expects RGB)
    # - 640x480 resolution (fast + accurate)
    config = picam2.create_preview_configuration(
        main={"format": "RGB888", "size": (640, 480)}
    )

    picam2.configure(config)
    picam2.start()  # Start camera stream

    print("[CAMERA] Pi Camera started via libcamera")

    # -----------------------------------------------------
    # Initialize MediaPipe Face Detection
    # -----------------------------------------------------
    mp_face = mp.solutions.face_detection.FaceDetection(
        model_selection=0,          # 0 = short-range (best for classrooms)
        min_detection_confidence=0.6
    )

    # -----------------------------------------------------
    # Load trained AI model (if exists)
    # -----------------------------------------------------
    clf = load_model_if_exists()
    if clf is None:
        system_message("Model Missing", "Train via Web")
        print("[WARNING] No trained model found")

    # -----------------------------------------------------
    # Main camera processing loop
    # -----------------------------------------------------
    while running:

        # Capture a frame from Pi Camera (already RGB)
        frame = picam2.capture_array()

        # MediaPipe expects RGB → frame already RGB
        results = mp_face.process(frame)

        # -------------------------------------------------
        # If at least one face is detected
        # -------------------------------------------------
        if results.detections:
            for detection in results.detections:

                # Convert RGB → BGR before OpenCV processing
                bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                # Extract face and generate embedding
                emb = crop_face_and_embed(bgr_frame, detection)

                # If embedding + model exist
                if emb is not None and clf is not None:

                    # Predict identity using trained model
                    user_id, confidence = predict_with_model(clf, emb)

                    # -------------------------------------
                    # If confidence is acceptable
                    # -------------------------------------
                    if confidence > 0.5:
                        with app.app_context():
                            today = datetime.now().date()

                            # Check if already marked today
                            exists = db.session.execute(
                                text("""
                                    SELECT 1 FROM attendance
                                    WHERE student_id = :sid
                                    AND DATE(timestamp) = :today
                                """),
                                {"sid": user_id, "today": today}
                            ).fetchone()

                            # Get user name for display
                            name = db.session.execute(
                                text("SELECT name FROM users WHERE user_id = :sid"),
                                {"sid": user_id}
                            ).scalar() or user_id

                            # ---------------------------------
                            # New attendance
                            # ---------------------------------
                            if not exists:
                                db.session.execute(
                                    text("""
                                        INSERT INTO attendance
                                        (student_id, class_id, timestamp, status)
                                        VALUES (:sid, 1, NOW(), 'present')
                                    """),
                                    {"sid": user_id}
                                )
                                db.session.commit()
                                attendance_success(name, confidence)
                            else:
                                attendance_duplicate(name)

                    else:
                        # Face detected but confidence too low
                        attendance_unknown()

                # Delay to prevent double marking same person
                time.sleep(2)

    # -----------------------------------------------------
    # Stop camera when loop exits
    # -----------------------------------------------------
    picam2.stop()
    print("[CAMERA] Pi Camera stopped")

# =========================================================
# SAFE SHUTDOWN HANDLER
# =========================================================
def shutdown_handler(signum, frame):
    """
    Ensures clean exit when Ctrl+C is pressed
    """
    global running
    print("\n[SHUTDOWN] Closing system...")
    running = False
    cleanup()      # Turn off GPIO safely
    sys.exit(0)

# Capture Ctrl+C and termination signals
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# =========================================================
# APPLICATION ENTRY POINT
# =========================================================
if __name__ == "__main__":
    print("[PI] Digital Attendance System Initializing...")

    # Start camera loop in background thread
    camera_thread = threading.Thread(
        target=camera_loop,
        daemon=True
    )
    camera_thread.start()

    # Start Flask web dashboard
    # Access via: http://<pi-ip>:5000
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )
