# 🛡️ Digital Facial Recognition Attendance System (Pi 5 Edition)

An autonomous, enterprise-grade attendance solution built for the Raspberry Pi 5. This system integrates real-time Computer Vision, localized I2C hardware feedback, and MLflow-tracked model training into a seamless "Plug-and-Play" appliance.

## 🚀 System Architecture

- **Hardware Layer**: Pi 5 (8GB) + Pi Camera Module 3 + I2C 16x2 LCD Display
- **Vision Engine**: Google MediaPipe (Face Detection) + FaceNet (Embeddings) + Scikit-Learn (Random Forest)
- **Tracking & MLOps**: MLflow integration on Port 5050 for monitoring training accuracy and model versioning
- **Persistence**: MySQL backend with SQLAlchemy ORM for attendance logging and student records
- **Deployment**: Fully headless via dual systemd services (Attendance AI + MLflow Server)

## 🛠️ Engineering Challenges & Solutions

### 1. LCD Garbage Value Glitch
- **Issue**: Random symbols during high CPU load
- **Root Cause**: I2C bus desynchronization
- **Solution**: Added 10-second stabilization delay, hardware reset routine, and potentiometer calibration

### 2. Pi 5 Camera Architecture
- **Issue**: `cv2.VideoCapture(0)` hangs on Pi 5's new camera stack
- **Solution**: Switched to YUV streaming via `rpicam-vid` with in-memory BGR conversion (<0.2s latency)

### 3. Autonomous Boot
- **Solution**: Dual systemd services (mlflow.service + attendance.service)

### 4. MLflow FileStore Limitations
- **Issue**: Error 500 on FileStore searches
- **Solution**: Configured system to ignore non-critical UI telemetry errors

## 📂 Project Structure

```
.
├── start_system.py
├── run_pi.py
├── app.py
├── hardware.py
├── model.py
├── manual_fix.py
├── mlflow.service
├── attendance.service
└── /dataset
```

## 📦 Installation

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements-pi.txt
mysql -u your_user -p attendance_db < schema.sql
```

## ⚙️ Enabling Autonomous Mode

```bash
sudo cp *.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mlflow.service attendance.service
sudo systemctl start mlflow.service attendance.service
```

## 📋 Operating Instructions

- **Boot**: Connect power; LCD shows "System Ready" in ~20 seconds
- **Monitor**: MLflow dashboard at `http://<pi-ip>:5050` (Current accuracy: 100%)
- **Dashboard**: View records at `http://<pi-ip>:5000`
- **Debug**: Run `sudo systemctl restart attendance.service`

---

**Author**: Abhisam Sharma  
**Tech Stack**: Raspberry Pi 5 | MediaPipe | MLflow | Flask  
**License**: MIT
