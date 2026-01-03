# =========================================================
# run_pi.py
# Digital Attendance System – Pi 5 High-Stability Version
# Uses persistent rpicam-vid stream to prevent hardware hangs
# =========================================================

import threading
import time
import signal
import sys
import subprocess
import os
from datetime import datetime

# Computer Vision & AI libraries
import cv2
import mediapipe as mp
import numpy as np

# Database & Flask
from sqlalchemy import text
from app import app, db

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
# PI 5 PERSISTENT CAPTURE LOGIC
# =========================================================
def get_single_frame():
    """
    Grabs a single frame using rpicam-vid. 
    By using --frames 1, we get the current state of the sensor 
    without the 'startup delay' of rpicam-still.
    """
    # -t 200: Wait 200ms to ensure the auto-exposure has a lock
    # --codec yuv420: Fastest raw format for the Pi 5 to output
    cmd = [
        "rpicam-vid",
        "--noproview",
        "--camera", "0",
        "--width", "640",
        "--height", "480",
        "--frames", "1",
        "--timeout", "200",
        "--codec", "yuv420",
        "-o", "-"
    ]
    try:
        # Run the command and capture the raw YUV byte stream
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3)
        
        if not process.stdout or len(process.stdout) == 0:
            return None

        # YUV420 data size for 640x480 is Width * Height * 1.5
        expected_size = int(640 * 480 * 1.5)
        raw_data = process.stdout[:expected_size]
        
        if len(raw_data) < expected_size:
            return None

        # Convert the raw YUV bytes into a BGR image that OpenCV can use
        # This is much faster and more reliable than decoding a JPEG/BMP
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

    # Initialize MediaPipe
    mp_face = mp.solutions.face_detection.FaceDetection(
        model_selection=0,
        min_detection_confidence=0.6
    )

    clf = load_model_if_exists()
    if clf is None:
        print("[WARNING] No trained model found. Please train via Web Dashboard.")

    while running:
        # 1. Capture Frame
        frame = get_single_frame()

        if frame is None:
            print("[CAMERA] Stdout empty. Resetting camera service...")
            # If hardware hangs, kill any stuck processes
            subprocess.run(["sudo", "pkill", "-9", "rpicam-vid"], stderr=subprocess.DEVNULL)
            time.sleep(1)
            continue

        # 2. Process Face Detection
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = mp_face.process(rgb_frame)

        if results.detections:
            for detection in results.detections:
                # 3. AI Recognition
                emb = crop_face_and_embed(frame, detection)

                if emb is not None and clf is not None:
                    user_id, confidence = predict_with_model(clf, emb)

                    if confidence > 0.5:
                        with app.app_context():
                            today = datetime.now().date()
                            
                            # Database Check
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

                # Cooldown to avoid double-triggers
                time.sleep(2)

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
    # Preliminary hardware reset to ensure the camera is free
    subprocess.run(["sudo", "pkill", "-9", "rpicam-still"], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "pkill", "-9", "rpicam-vid"], stderr=subprocess.DEVNULL)
    
    print("[START] Digital Attendance System Initializing...")
    camera_thread = threading.Thread(target=camera_loop, daemon=True)
    camera_thread.start()

    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)