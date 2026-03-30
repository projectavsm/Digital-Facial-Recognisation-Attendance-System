import threading, time, subprocess, os, cv2, numpy as np, mediapipe as mp
from flask import Response, jsonify, request
from app import app, db
from hardware import attendance_success, attendance_duplicate, attendance_unknown, system_message, cleanup
from model import load_model_if_exists, predict_with_model, crop_face_and_embed

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

@app.route('/trigger_attendance')
def trigger_attendance():
    global system_state
    system_state = "ALIGNING"
    threading.Timer(10.0, lambda: globals().update(system_state="SCANNING")).start()
    return jsonify({"status": "aligning"})

def camera_loop():
    global latest_frame, system_state
    mp_face = mp.solutions.face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.4)
    clf = load_model_if_exists()
    system_message("System Online", "Ready")

    while True:
        frame = get_pi_frame()
        if frame is None: continue
        latest_frame = frame.copy()

        if system_state == "SCANNING":
            results = mp_face.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if results.detections and clf:
                emb = crop_face_and_embed(frame, results.detections[0])
                if emb is not None:
                    sid, conf = predict_with_model(clf, emb)
                    if conf > 0.5:
                        with app.app_context():
                            name = db.session.execute(text("SELECT name FROM users WHERE user_id=:s"),{"s":sid}).scalar()
                            exists = db.session.execute(text("SELECT 1 FROM attendance WHERE student_id=:s AND DATE(timestamp)=CURDATE()"),{"s":sid}).fetchone()
                            if not exists:
                                db.session.execute(text("INSERT INTO attendance (student_id,class_id,timestamp,status) VALUES (:s,1,NOW(),'present')"),{"s":sid})
                                db.session.commit()
                                attendance_success(name, conf)
                            else: attendance_duplicate(name)
                    else: attendance_unknown()
            else: attendance_unknown()
            system_state = "IDLE"

if __name__ == "__main__":
    threading.Thread(target=camera_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, use_reloader=False)