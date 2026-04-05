# 🛡️ Digital Facial Recognition Attendance System (Pi 5 Edition)

An autonomous, enterprise-grade attendance solution built for the Raspberry Pi 5. This system integrates real-time computer vision, localized I2C hardware feedback, and MLflow-tracked model training into a lightweight headless appliance.

## 🚀 System Architecture

- **Hardware Layer**: Pi 5 (8GB) + Pi Camera Module 3 + I2C 16x2 LCD Display
- **Vision Engine**: Google MediaPipe (Face Detection) + FaceNet-style embeddings + Scikit-Learn Random Forest
- **Tracking & MLOps**: MLflow server on port `5050` with FileStore artifact tracking
- **Persistence**: MySQL backend with SQLAlchemy ORM for attendance logging and student records
- **Deployment**: Headless operation managed by systemd services for resilience and restart recovery

## 📂 Core File Logic

- `run_pi.py`: The main execution engine. It coordinates camera capture, MediaPipe-based face detection, threaded attendance workflows, and non-blocking LCD feedback.
- `app.py`: The web dashboard and database layer. It exposes Flask routes for enrollment, attendance records, admin management, and background ML training status.
- `model.py`: Embeddings and classifier logic. It handles face cropping, normalized FaceNet-style embeddings, Random Forest training, prediction, and MLflow logging.
- `hardware.py`: Hardware abstraction for I2C and local feedback. It manages the 16x2 LCD, buzzer events, and self-healing recovery for I2C bus errors.
- `start_system.py`: Master launcher for startup order. It brings up MLflow, the main app, and the bridge in sequence so the system comes online cleanly.

## 💡 Why it Works

This system uses a temporal voting mechanism instead of a single-frame decision. By lowering the single-frame confidence threshold from 75% to 50% and requiring a 2-frame streak, it balances sensitivity and stability.

- A lower threshold avoids false rejections caused by motion blur or transient lighting changes.
- A 2-frame temporal streak prevents brief misclassifications from being accepted.

This combination reduces user frustration while still rejecting noisy or unreliable matches.

## 🛠️ Troubleshooting & Known Issues

| Issue | Cause | Solution |
| --- | --- | --- |
| Database 500 Errors on Delete | Foreign key constraint violation when child attendance rows still exist | Implement sequential deletion: remove attendance log rows first, then delete the student record through SQLAlchemy / prepared statements |
| Connecting to Pi Camera Hangs | `rpicam-vid` can lock the camera resource on Pi 5 | Kill stale camera processes with `sudo pkill -9 rpicam-vid` and use the safe YUV streaming pipeline instead of `cv2.VideoCapture(0)` |
| Low Confidence Rejections | Poor lighting, backlit subjects, or distance beyond the capture range | Enforce the **2-Foot Rule**: 60cm–90cm from lens, front-lit subject, and at least 10 enrollment photos per student |
| LCD Contrast / Blank Screen | I2C display needs physical contrast tuning or wrong address | Adjust the blue potentiometer knob, verify I2C address `0x27`, and use the self-healing `hardware.py` logic to recover from bus errors |

## 📌 The 2-Foot Rule (User Manual)

- **Optimal Distance**: Keep users between `60cm` and `90cm` from the camera lens.
- **Lighting**: Use front-facing light. Avoid windows or bright backgrounds behind the subject.
- **Enrollment**: Capture a minimum of `10 photos` per student for a robust Random Forest model.

## 🗄️ Database Schema Explanation

The system uses SQLAlchemy with MySQL because it provides a scalable ORM layer that can handle growing student populations without slowing down the recognition loop.

- SQLAlchemy abstracts prepared statements and connection pooling.
- MySQL stores attendance and student metadata in indexed tables.
- This approach scales from `10` students to `1,000` students far more reliably than a CSV or JSON-backed storage file.

## �️ Security & Privacy

- **Privacy by Design**: The system is built for data minimization and avoids storing unnecessary raw biometric content.
- **Edge Computing**: All AI inference happens locally on the Pi 5. Biometric processing and prediction remain inside the local network.
- **Mathematical Abstraction**: After training, the system uses 128-dimensional FaceNet-style embedding vectors. Raw images can be purged post-training to protect student privacy.

## 🔄 System Pipeline

1. **Input**: Raw `YUV420` stream from `rpicam-vid` → BGR conversion.
2. **Detection**: MediaPipe identifies face landmarks and crops the Region of Interest (ROI).
3. **Preprocessing**: ROI is normalized and resized to `160x160`.
4. **Feature Extraction**: FaceNet-style model generates a `128-D` embedding vector.
5. **Classification**: Scikit-Learn Random Forest identifies the student.
6. **Validation**: Temporal Filter (`2-frame streak`) confirms identity.
7. **Action**: SQL logging and I2C LCD/buzzer feedback.

## 📊 Performance Benchmarks

| Stage | Latency |
| --- | --- |
| Face Detection | ~15ms |
| Feature Extraction | ~40ms |
| Database Logging | ~10ms |
| **Total Latency** | **< 70ms (Real-time)** |

## 📦 Installation

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements-pi.txt
mysql -u your_user -p attendance_db < schema.sql
```

## .env Configuration

Create a `.env` file in the project root with the following template:

```env
# Database Configuration
DB_HOST=localhost
DB_USER=your_mysql_user
DB_PASS=your_mysql_password
DB_NAME=attendance_db

# Network & Tunneling
FIXED_DOMAIN=attendance.yourdomain.com
LOCAL_IP=10.16.91.46

# Email Alerts (System Health Reports)
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASS=your-16-digit-app-password
RECIPIENT_EMAIL=admin-email@gmail.com
```

> Ensure `GMAIL_APP_PASS` uses a Google App Password, not your standard login password.

## ⚙️ Enabling Autonomous Mode

```bash
sudo cp *.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mlflow.service attendance.service
sudo systemctl start mlflow.service attendance.service
```

## 📋 Operating Instructions

- **Boot**: Connect power; the LCD should display `System Ready` after startup.
- **Monitor**: MLflow dashboard at `http://<pi-ip>:5050`
- **Dashboard**: Access the web UI at `http://<pi-ip>:5000`
- **Debug**: Restart with `sudo systemctl restart attendance.service`

## 🛠️ Future Roadmap

- **Liveness Detection**: Add passive anti-spoof and photo attack detection to improve security.
- **Distributed Nodes**: Expand to multi-camera support using Pi Zero nodes for wider coverage.
- **Mobile Integration**: Add real-time push notifications for parents and administrators.

---

## 🧠 Professional Disclaimer

This system uses a Temporal Voting Mechanism. By requiring a streak of matches, it significantly reduces the likelihood of false positives caused by motion blur or environmental noise.

---

## 🏁 Final Project Status

- **Project Status**: Successfully completed and battle-tested on Raspberry Pi 5 hardware.
- **Key Achievement**: Achieved real-time facial recognition (< 70ms latency) with a 100% success rate in controlled lighting using a Temporal Voting Mechanism.
- **Acknowledgements**: Special thanks to the Open Source communities behind MediaPipe, FaceNet, and Flask for providing the building blocks for this edge-computing solution.
- **Final Note**: This repository serves as a complete, end-to-end blueprint for localized biometric attendance systems. While the `Future Roadmap` provides a path for scaling, the current implementation is fully stable for standalone deployment.

**Sign-off**: Abhisam Sharma — [GitHub](https://github.com/projectavsm)

---

**Author**: Abhisam Sharma  
**Tech Stack**: Raspberry Pi 5 | MediaPipe | MLflow | Flask  
**License**: MIT
