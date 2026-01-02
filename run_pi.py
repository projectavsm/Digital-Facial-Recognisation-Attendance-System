import threading
import time
import signal
import sys
import cv2            # OpenCV for camera handling
import mediapipe as mp # AI for face detection
from datetime import datetime
from sqlalchemy import text

# Import the parts we set up earlier
from app import app, db
from hardware import (
    attendance_success,
    attendance_duplicate,
    attendance_unknown,
    system_message,
    cleanup
)
from model import load_model_if_exists, predict_with_model, crop_face_and_embed

# Global flag to keep the system running
running = True

# ---------------------------------------------------------
# CAMERA & RECOGNITION LOOP
# ---------------------------------------------------------
def camera_loop():
    """
    Main background thread:
    1. Captures frames from the camera
    2. Detects faces using MediaPipe
    3. Crops and converts faces to embeddings
    4. Predicts user ID and marks attendance in MySQL
    """
    system_message("System Ready", "Scanning faces")
    
    # Initialize the camera (Index 0 is standard Pi Camera)
    cap = cv2.VideoCapture(0)
    
    # Initialize MediaPipe Face Detection
    mp_face = mp.solutions.face_detection.FaceDetection(
        model_selection=0, # 0 for short-range (2 meters), 1 for long-range
        min_detection_confidence=0.6 # Only process clear faces
    )
    
    # Load the Random Forest model we fixed earlier
    clf = load_model_if_exists()
    if clf is None:
        print("[WARNING] model.pkl not found. System will only scan, not recognize.")
        system_message("Model Missing", "Train via Web")

    print("[CAMERA] Loop started...")

    while running:
        success, frame = cap.read()
        if not success:
            time.sleep(0.1)
            continue

        # MediaPipe requires RGB images, OpenCV captures in BGR
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = mp_face.process(rgb_frame)

        # If faces are detected in the frame
        if results.detections:
            for detection in results.detections:
                # 1. Convert the face into a mathematical vector (embedding)
                emb = crop_face_and_embed(frame, detection)
                
                if emb is not None and clf is not None:
                    # 2. Ask the AI model who this is
                    user_id, confidence = predict_with_model(clf, emb)
                    
                    # 3. If confidence is high enough, talk to the Database
                    if confidence > 0.5:
                        with app.app_context():
                            today = datetime.now().date()
                            
                            # Check if already marked today in MySQL
                            exists = db.session.execute(
                                text("SELECT 1 FROM attendance WHERE student_id = :sid AND DATE(timestamp) = :today"),
                                {"sid": user_id, "today": today}
                            ).fetchone()

                            # Fetch the name for the LCD display
                            name = db.session.execute(
                                text("SELECT name FROM users WHERE user_id = :sid"),
                                {"sid": user_id}
                            ).scalar() or user_id

                            if not exists:
                                # Mark new attendance
                                db.session.execute(
                                    text("INSERT INTO attendance (student_id, class_id, timestamp, status) VALUES (:sid, 1, NOW(), 'present')"),
                                    {"sid": user_id}
                                )
                                db.session.commit()
                                attendance_success(name, confidence)
                            else:
                                attendance_duplicate(name)
                    else:
                        # Face detected but AI isn't sure who it is
                        attendance_unknown()
                
                # Sleep for 2 seconds after a detection to prevent double-marking the same person
                time.sleep(2)

    # Release hardware when the thread stops
    cap.release()

# ---------------------------------------------------------
# SHUTDOWN CLEANUP
# ---------------------------------------------------------
def shutdown_handler(signum, frame):
    """Safely closes GPIO and Camera when you press Ctrl+C"""
    global running
    print("\n[SHUTDOWN] Closing system...")
    running = False
    cleanup() # From hardware.py
    sys.exit(0)

# Listen for termination signals (Ctrl+C)
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# ---------------------------------------------------------
# STARTUP
# ---------------------------------------------------------
if __name__ == "__main__":
    print("[PI] Digital Attendance System Initializing...")
    
    # Start the camera recognition in a background thread
    camera_thread = threading.Thread(target=camera_loop, daemon=True)
    camera_thread.start()

    # Start the Flask Web Dashboard on the main thread
    # Access this via http://<your-pi-ip>:5000
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)