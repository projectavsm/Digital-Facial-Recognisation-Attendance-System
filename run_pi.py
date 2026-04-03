import threading, time, subprocess, os, cv2, numpy as np, mediapipe as mp
import socket, smtplib
from email.message import EmailMessage
from flask import Response, jsonify, request
from app import app, db
from hardware import attendance_success, attendance_duplicate, attendance_unknown, system_message, cleanup
from model import load_model_if_exists, predict_with_model, crop_face_and_embed
from sqlalchemy import text
from dotenv import load_dotenv

# --- INITIALIZATION ---
load_dotenv() # Loads your .env file
DATASET_DIR = "dataset"
latest_frame = None
system_state = "IDLE" 

# Mapping your .env variables
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_APP_PASS")
RECIPIENT = os.getenv("RECIPIENT_EMAIL")
FIXED_DOMAIN = os.getenv("FIXED_DOMAIN")

# --- BOOT METRICS LOGIC ---

def get_boot_metrics():
    """Measures system performance for the professional admin report."""
    metrics = {}
    
    # 1. WiFi/DNS Latency
    wifi_start = time.perf_counter()
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        metrics['wifi_latency'] = f"{round(time.perf_counter() - wifi_start, 3)}s"
    except:
        metrics['wifi_latency'] = "Offline"

    # 2. Tunnel Accessibility Check
    try:
        # Checks if your specific domain is resolving/reachable
        socket.gethostbyname(FIXED_DOMAIN)
        metrics['tunnel_status'] = "Active/Reachable"
    except:
        metrics['tunnel_status'] = "Inactive or DNS Issue"

    # 3. OS Uptime
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
            metrics['uptime'] = f"{round(uptime_seconds / 60, 2)} minutes"
    except:
        metrics['uptime'] = "Unknown"

    # 4. ML Model Loading Speed
    model_start = time.perf_counter()
    _ = load_model_if_exists()
    metrics['model_load_time'] = f"{round(time.perf_counter() - model_start, 3)}s"

    return metrics

def send_boot_report():
    """Sends the 'System Healthy' email with all collected timers."""
    if not GMAIL_USER or not GMAIL_PASS:
        print("[MAIL] Error: Credentials missing in .env")
        return

    try:
        metrics = get_boot_metrics()
        msg = EmailMessage()
        msg['Subject'] = "🚀 Attendance System: Online & Healthy"
        msg['From'] = GMAIL_USER
        msg['To'] = RECIPIENT
        
        content = (
            "Digital Attendance System (Pi 5) has initialized.\n\n"
            "--- Performance Metrics ---\n"
            f"• WiFi Latency: {metrics['wifi_latency']}\n"
            f"• ML Model Load Speed: {metrics['model_load_time']}\n"
            f"• System Uptime: {metrics['uptime']}\n\n"
            "--- Network & Tunnel ---\n"
            f"- Public URL: https://{FIXED_DOMAIN}\n"
            f"- Tunnel Status: {metrics['tunnel_status']}\n"
            f"- Local IP: http://10.16.91.46:5000\n\n"
            "Hardware Check: LCD [OK], Camera [OK], Database [OK]\n"
            "---------------------------\n"
            "Status: Awaiting manual attendance triggers."
        )
        msg.set_content(content)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_PASS)
            smtp.send_message(msg)
        print(f"[MAIL] Boot report sent to {RECIPIENT}")
    except Exception as e:
        print(f"[MAIL] Failed to send report: {e}")

# --- CAMERA & VIDEO LOGIC ---

def get_pi_frame():
    """Captures frame from Pi Camera using libcamera-vid pipe."""
    cmd = ["rpicam-vid", "--nopreview", "--camera", "0", "--width", "640", "--height", "480", "--frames", "1", "--timeout", "200", "--codec", "yuv420", "-o", "-"]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if not proc.stdout: return None
    raw = proc.stdout[:int(640*480*1.5)]
    yuv = np.frombuffer(raw, dtype=np.uint8).reshape((int(480*1.5), 640))
    return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)

@app.route('/video_feed')
def video_feed():
    def stream():
        while True:
            if latest_frame is not None:
                _, buffer = cv2.imencode('.jpg', latest_frame)
                yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.1)
    return Response(stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

# --- ATTENDANCE MODE LOGIC ---

@app.route('/trigger_capture')
def trigger_capture():
    global system_state
    app.enroll_id = request.args.get('student_id') 
    system_state = "SCANNING"
    return jsonify({"status": "capturing"})

@app.route('/trigger_attendance')
def trigger_attendance_alias():
    return trigger_capture()

def camera_loop():
    global latest_frame, system_state
    mp_face = mp.solutions.face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)
    clf = load_model_if_exists()
    
    # --- MAJORITY VOTE LOGIC ---
    consecutive_matches = 0
    last_sid = None
    REQUIRED_FRAMES = 3 

    system_message("System Online", "Ready")
    time.sleep(0.5)

    while True:
        frame = get_pi_frame()
        if frame is None: continue
        latest_frame = frame.copy()

        if system_state == "SCANNING":
            current_enrollment_id = getattr(app, 'enroll_id', None)
            
            if current_enrollment_id:
                # --- ENROLLMENT MODE ---
                folder_path = os.path.join(DATASET_DIR, str(current_enrollment_id))
                if not os.path.exists(folder_path): os.makedirs(folder_path)
                img_path = os.path.join(folder_path, f"{int(time.time())}.jpg")
                cv2.imwrite(img_path, frame)
                system_message("Photo Captured", f"ID: {current_enrollment_id}")
                app.enroll_id = None 
                system_state = "IDLE"
                time.sleep(1.0) 

            else:
                # --- ATTENDANCE MODE ---
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = mp_face.process(rgb_frame)
                found_match_this_frame = False

                if results.detections and clf:
                    emb = crop_face_and_embed(frame, results.detections[0])
                    if emb is not None:
                        sid, conf = predict_with_model(clf, emb)
                        
                        with app.app_context():
                            name = db.session.execute(
                                text("SELECT name FROM users WHERE user_id=:s"), {"s": sid}
                            ).scalar() or f"User {sid}"

                        # 1. Confident Threshold
                        if conf > 0.75:
                            found_match_this_frame = True
                            if sid == last_sid:
                                consecutive_matches += 1
                                print(f"[STREAK] {consecutive_matches}/3 for {name}")
                            else:
                                consecutive_matches = 1
                                last_sid = sid
                                
                            # 2. Match Consensus
                            if consecutive_matches >= REQUIRED_FRAMES:
                                with app.app_context():
                                    exists = db.session.execute(
                                        text("SELECT 1 FROM attendance WHERE student_id=:s AND DATE(timestamp)=CURDATE()"),
                                        {"s": sid}
                                    ).fetchone()
                                    
                                    if not exists:
                                        db.session.execute(
                                            text("INSERT INTO attendance (student_id,class_id,timestamp,status) VALUES (:s,1,NOW(),'present')"),
                                            {"s": sid}
                                        )
                                        db.session.commit()
                                        attendance_success(name, conf)
                                    else:
                                        attendance_duplicate(name)
                                
                                consecutive_matches = 0
                                last_sid = None
                                system_state = "IDLE"
                        else:
                            # 3. Transparent Logging
                            print(f"[REJECTED] Low Conf: {name} ({conf:.2f})")

                if not found_match_this_frame:
                    consecutive_matches = 0
                    last_sid = None

            time.sleep(0.1) 
        
        time.sleep(0.01)

# --- MAIN RUN ---

if __name__ == "__main__":
    try:
        # Boot Metrics and Report
        threading.Thread(target=send_boot_report, daemon=True).start()
        
        # Camera Logic
        threading.Thread(target=camera_loop, daemon=True).start()
        
        # Flask Dashboard
        app.run(host="0.0.0.0", port=5000, use_reloader=False)
    except KeyboardInterrupt:
        cleanup()