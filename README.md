# 🛡️ Digital Facial Recognition Attendance System (Pi 5 Edition)

An automated, end-to-end attendance management system leveraging Raspberry Pi 5, MediaPipe, and Flask. This system bridges the gap between raw Computer Vision and a professional Web Dashboard, featuring a robust MySQL backend and a fully autonomous "Plug-and-Play" deployment architecture.

## 🚀 System Architecture

- **Hardware Layer:** Pi 5 + Pi Camera Module 3. Uses rpicam-vid YUV streaming to bypass V4L2/Libcamera locks that typically crash OpenCV on Pi 5.
- **Logic Layer:**
    - Face Processing: Google MediaPipe (Real-time detection) + FaceNet embeddings
    - Classification: Scikit-Learn Random Forest Classifier
    - Database Sync: Dual-lookup logic mapping Student IDs to physical folders
- **Presentation Layer:** Flask-based Glassmorphism UI providing real-time monitoring and Admin Directory
- **Connectivity Layer:** Cloudflare Zero-Trust Tunneling for secure, remote access without port forwarding

## ✨ Key Features

- Autonomous "Appliance" Mode: System boots automatically on power-up using systemd with integrated Wi-Fi-ready checks
- Cloudflare Remote Bridge: Automatic generation of a secure public URL on boot, emailed to the administrator
- Dynamic Admin Directory: Smart portal scanning MySQL database and /dataset folder for registered students
- Hardened Duplicate Prevention: MySQL UNIQUE composite key ensures students are marked "Present" only once per day
- Zero-Latency Dashboard: Optimized YUV-to-BGR conversion reduces inference lag to under 0.2s per frame

## 📂 Project Structure

```
Digital-Facial-Recognisation-Attendance-System/
├── start_system.py             # Main entry point (Automation wrapper)
|--- bridge.py
├── run_pi.py                   # Main Execution Loop (Camera + Server)
├── app.py                      # Flask & SQLAlchemy Configuration
├── hardware.py                 # GPIO, Buzzer, and LCD controls
├── model.py                    # AI/MediaPipe Face Recognition logic
├── schema.sql                  # MySQL Database Structure
├── requirements-pi.txt         # Dependencies optimized for Pi 5
├── /etc/systemd/system/        # attendance.service (System boot config)
└── ... (static/templates/etc)
```

## 🔍 Automation & Stability Fixes

- **Headless Deployment:** Configured via systemd to handle boot-time race conditions (waits for network-online.target)
- **SMTP Notification:** Automated email dispatch containing the dynamic Cloudflare tunnel link upon successful initialization
- **Self-Healing:** Restart=always logic ensures the service recovers automatically from power blips or software crashes
- **Permission Bridge:** Symbolic links facilitate web-viewable dataset access while maintaining local security

## 📦 Installation & Setup

### Clone and Environment:

```bash
git clone https://github.com/your-username/Digital-Attendance-System.git
cd Digital-Attendance-System
python -m venv venv
source venv/bin/activate
pip install -r requirements-pi.txt
```

### Database & Assets:

```bash
mysql -u your_user -p attendance_db < schema.sql
ln -s $(pwd)/dataset $(pwd)/static/dataset_link
```

### Enable Auto-Boot (Headless Mode):

```bash
sudo cp attendance.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable attendance.service
sudo systemctl start attendance.service
```

## ⚙️ Operating the System

1. **Power On:** Connect the Pi 5 to power
2. **Wait:** The system takes ~2:50 minutes to boot, stabilize Wi-Fi, and establish the secure tunnel
3. **Access:** Check your registered email for the Cloudflare Link. Use this URL to access the dashboard from any device globally

---

**Author:** Abhisam Sharma | **License:** MIT