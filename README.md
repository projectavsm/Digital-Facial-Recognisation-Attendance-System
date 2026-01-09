# 🛡️ Digital Facial Recognition Attendance System (Pi 5 Edition)

An automated, end-to-end attendance management system leveraging Raspberry Pi 5, MediaPipe, and Flask. This system bridges the gap between raw Computer Vision and a professional Web Dashboard, featuring a robust MySQL backend and a dynamic Admin suite.

## 🚀 System Architecture

- **Hardware Layer:** Pi 5 + Pi Camera Module 3. We utilize rpicam-vid YUV streaming to bypass the V4L2/Libcamera locks that typically crash OpenCV on the Pi 5.
- **Logic Layer:**
    - Face Processing: Google MediaPipe (Real-time detection) + FaceNet embeddings
    - Classification: Scikit-Learn Random Forest Classifier
    - Database Sync: Dual-lookup logic mapping Student IDs to Physical Folders
- **Presentation Layer:** Flask-based Glassmorphism UI providing a real-time monitor and Admin Directory

## ✨ Key Features

- **Dynamic Admin Directory:** Smart portal scanning MySQL database and `/dataset` folder for registered students
- **Image Routing Bridge:** Custom Flask routes bypass local file system restrictions
- **Hardened Duplicate Prevention:** MySQL UNIQUE composite key ensures students marked "Present" once per day
- **Zero-Latency Dashboard:** Optimized YUV-to-BGR conversion reduces inference lag to under 0.2s per frame

## 📂 Project Structure

Digital-Facial-Recognisation-Attendance-System/
├── app.py                      # Flask & SQLAlchemy Configuration
├── hardware.py                 # GPIO, Buzzer, and LCD controls
├── model.py                    # AI/MediaPipe Face Recognition logic
├── run_pi.py                   # Main Execution Loop (Camera + Server)
├── schema.sql                  # MySQL Database Structure
├── requirements-pi.txt         # Dependencies optimized for Pi 5
├── README.md                   # System Documentation
├── .gitignore                  # Git Exclusion rules (ignores venv/dataset)
│
├── static/                     # Web Assets (Public)
│   ├── css/
│   │   └── style.css           # Custom Glassmorphism styles
│   ├── images/
│   │   └── bg.png              # Dashboard background
│   └── js/
│       ├── dashboard.js        # Training & Chart logic
│       ├── camera_add_student.js
│       └── camera_mark.js      # Recognition view logic
│
├── templates/                  # HTML Views (Jinja2)
│   ├── index.html              # Main Dashboard
│   ├── admin_directory.html    # Student Selection Menu
│   ├── admin_view.html         # Individual Dataset Viewer
│   ├── add_student.html        # Enrollment Page
│   ├── mark_attendance.html    # Live Scanning Page
│   └── attendance_record.html  # SQL Record Viewer
│
└── tests & tools/              # Maintenance scripts
    ├── manual_fix.py
    └── test_db.py

## 🔍 Stability Fixes

- Permission Bridge: Symbolic link for dataset access
- Numerical Identity Mapping: Student ID-based directory system
- Subprocess Lockdown: pkill cleanup sequence

## 📦 Installation

```bash
git clone https://github.com/your-username/Digital-Attendance-System.git
cd Digital-Attendance-System
python -m venv venv
source venv/bin/activate
pip install -r requirements-pi.txt
ln -s /home/pi/Digital-Attendance-System/dataset /home/pi/Digital-Attendance-System/static/dataset_link
mysql -u your_user -p attendance_db < schema.sql
```

## ⚙️ Operating the System

- **Main Dashboard:** `http://<your-pi-ip>:5000`
- **Admin Directory:** `http://<your-pi-ip>:5000/admin/login` (Password: `admin123`)

**Author:** Abhisam Sharma | **License:** MIT
