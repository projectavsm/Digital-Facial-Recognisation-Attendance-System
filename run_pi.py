# =========================================================
# run_pi.py
# Digital Attendance System – Raspberry Pi 5 Refined Version
# Optimized for Pi 5 ISP (PiSP) using immediate capture
# =========================================================

import threading
import time
import signal
import sys
import subprocess  # Required to run rpicam-still as a subprocess
from datetime import datetime

# Computer Vision & AI libraries
import cv2           # Image processing (OpenCV)
import mediapipe as mp
import numpy as np

# Database & Flask
from sqlalchemy import text
from app import app, db

# Hardware & UI helpers (LCD, Buzzer, GPIO)
from hardware import (
    attendance_success,   # Success feedback (Green LED/Buzzer)
    attendance_duplicate, # Duplicate feedback (Yellow LED)
    attendance_unknown,   # Unknown feedback (Red LED)
    system_message,       # LCD status update
    cleanup               # GPIO safety cleanup
)

# AI Model helpers
from model import (
    load_model_if_exists,   # Loads your trained facial recognition model
    predict_with_model,     # Matches embeddings against the model
    crop_face_and_embed     # Detects face and generates 128D vector
)

# Global control flag to allow clean exit via Ctrl+C
running = True

# =========================================================
# REFINED: PI 5 HARDWARE CAPTURE FUNCTION
# =========================================================
def capture_frame_pi5():
    """
    Refined Pi 5 capture: uses --immediate and --timeout to prevent 
    empty buffers caused by the Pi 5's default warm-up delay.
    """
    # --noproview: Disables the HDMI preview window (essential for headless/background)
    # --timeout 1: Sets the total time the camera stays open to 1ms
    # --immediate: Force capture the first frame without waiting for auto-exposure
    # -e bmp: BMP format is uncompressed and decodes faster than JPG
    # -o -: Sends the image data to standard output (RAM)
    cmd = [
        "rpicam-still", 
        "--noproview", 
        "--timeout", "1", 
        "--immediate",
        "--width", "640", 
        "--height", "480", 
        "-e", "bmp", 
        "-o", "-"
    ]
    try:
        # Run command with a 5-second process timeout to prevent hanging the system
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        
        # Check if the process actually returned data
        if not process.stdout or len(process.stdout) == 0:
            print("[CAMERA] Error: Stdout is empty. Check camera connection.")
            return None
            
        # Convert the raw byte stream from memory into a numpy array
        image_array = np.frombuffer(process.stdout, dtype=np.uint8)
        
        # Decode the byte array into a standard OpenCV BGR image
        frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        
        if frame is None:
            # Occurs if the BMP header is corrupted or incomplete
            print("[CAMERA] Error: Failed to decode image buffer.")
            return None
            
        return frame
    except subprocess.TimeoutExpired:
        print("[CAMERA] Error: Capture process timed out.")
        return None
    except Exception as e:
        print(f"[CAMERA ERROR] Unexpected error: {e}")
        return None

# =========================================================
# MAIN RECOGNITION THREAD
# =========================================================
def camera_loop():
    """
    Continuous loop: Captures frame -> Detects Face -> Recognizes -> Logs to DB.
    """
    system_message("System Ready", "Scanning faces")
    print("[PI 5] Camera System Online (Refined Subprocess Mode)")

    # Initialize MediaPipe Face Detection
    mp_face = mp.solutions.face_detection.FaceDetection(
        model_selection=0,           # 0 for short-range (best for desk/entryway)
        min_detection_confidence=0.6 # Filter out false positive "face-like" objects
    )

    # Load the AI classifier
    clf = load_model_if_exists()
    if clf is None:
        system_message("Model Missing", "Train via Web")
        print("[WARNING] No trained model found. System will detect faces but won't recognize.")

    # Main Loop
    while running:
        # 1. Capture the image using the refined Pi 5 function
        bgr_frame = capture_frame_pi5()

        if bgr_frame is None:
            # Wait briefly before retrying if a frame capture failed
            time.sleep(0.5)
            continue

        # 2. Convert BGR (OpenCV) to RGB (MediaPipe)
        rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        results = mp_face.process(rgb_frame)

        # 3. Process Detections
        if results.detections:
            for detection in results.detections:
                # Generate embedding (vector) for the detected face
                emb = crop_face_and_embed(bgr_frame, detection)

                if emb is not None and clf is not None:
                    # Run the vector through your trained model
                    user_id, confidence = predict_with_model(clf, emb)

                    # Threshold: 50% confidence required
                    if confidence > 0.5:
                        with app.app_context():
                            today = datetime.now().date()
                            
                            # Check if attendance is already recorded for today
                            exists = db.session.execute(
                                text("""
                                    SELECT 1 FROM attendance
                                    WHERE student_id = :sid
                                    AND DATE(timestamp) = :today
                                """),
                                {"sid": user_id, "today": today}
                            ).fetchone()

                            # Fetch the name of the recognized user
                            name = db.session.execute(
                                text("SELECT name FROM users WHERE user_id = :sid"),
                                {"sid": user_id}
                            ).scalar() or user_id

                            if not exists:
                                # Insert new attendance record
                                db.session.execute(
                                    text("""
                                        INSERT INTO attendance
                                        (student_id, class_id, timestamp, status)
                                        VALUES (:sid, 1, NOW(), 'present')
                                    """),
                                    {"sid": user_id}
                                )
                                db.session.commit()
                                print(f"[SUCCESS] Attendance: {name} ({confidence*100:.1f}%)")
                                attendance_success(name, confidence)
                            else:
                                print(f"[INFO] {name} already marked for today.")
                                attendance_duplicate(name)
                    else:
                        # Confidence below 50%
                        print("[INFO] Face detected but unrecognized.")
                        attendance_unknown()

                # Anti-spam delay: prevents recording the same face 10 times in a row
                time.sleep(2)

    print("[CAMERA] Shutdown: Camera loop stopped.")

# =========================================================
# SYSTEM UTILITIES
# =========================================================
def shutdown_handler(signum, frame):
    """
    Ensures the system exits cleanly when you press Ctrl+C.
    """
    global running
    print("\n[SHUTDOWN] Cleaning up and exiting...")
    running = False
    cleanup()  # Hardware cleanup (LCD/LEDs)
    sys.exit(0)

# Attach listeners for termination signals
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# =========================================================
# MAIN ENTRY POINT
# =========================================================
if __name__ == "__main__":
    print("[START] Digital Attendance System Initializing...")
    
    # 1. Run Camera recognition in a background thread
    camera_thread = threading.Thread(target=camera_loop, daemon=True)
    camera_thread.start()

    # 2. Run Flask Web Dashboard on the main thread
    # host="0.0.0.0" makes it accessible to other devices on your WiFi
    app.run(
        host="0.0.0.0", 
        port=5000, 
        debug=False, 
        use_reloader=False 
    )