import threading, time, subprocess, os, cv2, numpy as np, mediapipe as mp
from flask import Response, jsonify, request
from app import app, db
from hardware import attendance_success, attendance_duplicate, attendance_unknown, system_message, cleanup
from model import load_model_if_exists, predict_with_model, crop_face_and_embed
from sqlalchemy import text
DATASET_DIR = "dataset"
latest_frame = None
system_state = "IDLE" # IDLE, ALIGNING, SCANNING

def get_pi_frame():
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

@app.route('/trigger_capture')
def trigger_capture():
    global system_state
    app.enroll_id = request.args.get('student_id') # Store the ID for the camera loop
    system_state = "SCANNING"
    return jsonify({"status": "capturing"})

@app.route('/trigger_attendance')
def trigger_attendance_alias():
    return trigger_capture() # Just calls the same function

def camera_loop():
    global latest_frame, system_state
    mp_face = mp.solutions.face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)
    clf = load_model_if_exists()
    
    # --- MAJORITY VOTE VARIABLES ---
    consecutive_matches = 0
    last_sid = None
    REQUIRED_FRAMES = 3 
    # -------------------------------

    system_message("System Online", "Ready")
    time.sleep(0.5)

    while True:
        frame = get_pi_frame()
        if frame is None: continue
        latest_frame = frame.copy()

        if system_state == "SCANNING":
            current_enrollment_id = getattr(app, 'enroll_id', None)
            
            if current_enrollment_id:
                # --- ENROLLMENT MODE --- (Keep as is)
                folder_path = os.path.join(DATASET_DIR, str(current_enrollment_id))
                if not os.path.exists(folder_path): os.makedirs(folder_path)
                img_path = os.path.join(folder_path, f"{int(time.time())}.jpg")
                cv2.imwrite(img_path, frame)
                system_message("Photo Captured", f"ID: {current_enrollment_id}")
                app.enroll_id = None 
                system_state = "IDLE"
                time.sleep(1.0) 

            else:
                # --- ATTENDANCE MODE (Merged Logic) ---
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = mp_face.process(rgb_frame)
                
                found_match_this_frame = False

                if results.detections and clf:
                    emb = crop_face_and_embed(frame, results.detections[0])
                    if emb is not None:
                        sid, conf = predict_with_model(clf, emb)
                        
                        # --- 1. DEBUG: Get name immediately for logging ---
                        with app.app_context():
                            predicted_name = db.session.execute(
                                text("SELECT name FROM users WHERE user_id=:s"),
                                {"s": sid}
                            ).scalar() or f"User {sid}"

                        # --- 2. THRESHOLD CHECK ---
                        if conf > 0.75:
                            found_match_this_frame = True
                            if sid == last_sid:
                                consecutive_matches += 1
                                print(f"[STREAK] {consecutive_matches}/3 for {predicted_name}")
                            else:
                                consecutive_matches = 1
                                last_sid = sid
                                
                            # --- 3. MAJORITY VOTE CHECK ---
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
                                        attendance_success(predicted_name, conf)
                                    else:
                                        attendance_duplicate(predicted_name)
                                
                                # Reset and go IDLE only after full success
                                consecutive_matches = 0
                                last_sid = None
                                system_state = "IDLE"
                        else:
                            # LOG: Even if rejected, we show what the AI thought
                            print(f"[REJECTED] Tentative: {predicted_name} ({conf:.2f}) - Below 0.75")
                            # Optional: attendance_unknown() call could go here if you want LCD to flicker "Unknown"

                # If no face or low confidence, reset the streak
                if not found_match_this_frame:
                    consecutive_matches = 0
                    last_sid = None

            time.sleep(0.1) 
        
        time.sleep(0.01)

if __name__ == "__main__":
    threading.Thread(target=camera_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, use_reloader=False)