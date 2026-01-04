# 🛡️ Digital Facial Recognition Attendance System (Pi 5 Edition)

An automated attendance management system leveraging Raspberry Pi 5, MediaPipe, and Flask. This system identifies individuals in real-time, logs attendance to a MySQL database with hardware-level duplicate prevention, and provides a password-protected admin suite for dataset management.

## 🚀 System Architecture

The system operates in three distinct layers:

- **Hardware Layer:** Raspberry Pi 5 + Pi Camera Module (using persistent YUV streaming via rpicam-vid to bypass Libcamera locks)
- **Logic Layer:**
    - Detection: Google MediaPipe Face Detection (Modern AI) or OpenCV Haar Cascades (Legacy/Manual)
    - Recognition: FaceNet-inspired Grayscale Embeddings + Scikit-Learn Random Forest Classifier
    - Training: Automated via Web UI or manual override via force_train.py
- **Presentation Layer:** Flask Web Dashboard featuring a Glassmorphism UI and Admin Dataset Viewer

## ✨ Key Features

- **High-Stability Capture:** Uses rpicam-vid raw byte-streaming to prevent camera hang issues on Pi 5
- **Dynamic Admin Panel:** Automatically scans the dataset/ directory with high-resolution face crop viewing
- **Glassmorphism UI:** Modernized translucent dashboard with real-time system status indicators
- **Database-Level Duplicate Prevention:** MySQL UNIQUE index ensures one "Present" mark per student per day
- **Dual Training Support:**
    - `model.py`: High-accuracy MediaPipe training via Dashboard
    - `force_train.py`: Robust manual training using Haar Cascades

## 🔍 Stability Fixes & Lessons Learned

### ✅ What Worked
- **YUV Streaming:** Reduced capture latency from 2.5s to 0.2s
- **Static Symlinking:** Efficient Flask image serving without data duplication
- **Subprocess Cleanup:** Prevents zombie camera processes on startup

### ❌ Challenges Overcome
- **V4L2 Interface:** Raw subprocess streaming is required for Pi 5 stability
- **Thermal Management:** Active cooling fan needed to prevent throttling during AI inference

## 📦 Installation & Setup

### 1. Environment Setup

```bash
git clone https://github.com/your-username/Digital-Attendance-System.git
cd Digital-Attendance-System
python -m venv venv
source venv/bin/activate
pip install -r requirements-pi.txt
```

### 2. Static Bridge Setup

```bash
ln -s /home/pi/Digital-Attendance-System/dataset /home/pi/Digital-Attendance-System/static/dataset_link
```

### 3. Database Initialization

```bash
mysql -u your_user -p attendance_db < schema.sql
```

## ⚙️ Running the System

### Manual AI Training

```bash
python force_train.py
```

### Start Live System

```bash
python run_pi.py
```

### Access the System

- **Dashboard:** `http://<your-pi-ip>:5000`
- **Admin Panel:** `http://<your-pi-ip>:5000/admin/login` (Password: admin123)

## 🗂️ Project Structure

```
├── run_pi.py         # Main execution loop
├── force_train.py    # Manual training
├── model.py          # AI inference & training
├── app.py            # Flask & SQLAlchemy
├── hardware.py       # GPIO controls
├── dataset/          # Face images
├── models/           # model.pkl
├── templates/
│   ├── index.html    # Dashboard
│   └── admin_view.html
└── static/
        └── dataset_link  # Symbolic link
```

## 📄 Maintenance

- **Laptop:** `git add .` → `git commit` → `git push origin main`
- **Pi:** `git pull origin main`

> **Note:** Optimized for BCM2712 (Pi 5). Running on standard laptop will fail.

**Author:** Abhisam Sharma  
**License:** MIT
