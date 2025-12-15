# Digital Facial Recognition Attendance System

The **Digital Facial Recognition Attendance System** is an advanced, automated system designed to track and manage attendance efficiently using facial recognition technology. Unlike traditional methods such as manual registers or RFID cards, this system leverages computer vision and AI to identify individuals in real-time, ensuring accuracy, security, and time-saving management.

---

## ✨ Key Features

- **Facial Recognition**: Detects and recognizes faces in real-time using AI and deep learning. Each person is uniquely identified to prevent proxy attendance.
- **Automated Attendance Logging**: Marks attendance automatically, eliminating manual entry errors.
- **Database Integration**: Stores records securely in SQLite/MySQL for easy retrieval, analysis, and reporting.
- **User Management**: Admins can add, update, or remove users and manage facial data.
- **Reporting & Analytics**: Generates daily, weekly, or monthly attendance reports with visual graphs.
- **Security & Accuracy**: Works in varied lighting and recognizes faces with masks or glasses.
- **GUI Dashboard**: Interactive web dashboard for admins and teachers to manage attendance.
- **Optional Notifications**: Can send email or SMS alerts about attendance status.

---

## 📍 Applications

- Schools, colleges, and universities
- Corporate offices for employee attendance tracking
- Workshops, seminars, and training programs

---

## 🛠️ Technology Stack

- **Programming Language**: Python
- **Libraries/Frameworks**: OpenCV, Mediapipe, scikit-learn, Flask, face recognition libraries
- **Database**: SQLite3 or MySQL
- **GUI**: HTML, CSS, JavaScript, Web-based dashboard
- **Optional**: Email/SMS APIs

---

## 💡 Benefits

- Reduces manual effort and paperwork
- Ensures accuracy and prevents fraudulent attendance
- Provides real-time data and analytics
- Scalable for institutions of any size

---

## 📦 Installation & Setup

1. **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/Digital-Facial-Recognisation-Attendance-System.git
    cd Digital-Facial-Recognisation-Attendance-System
    ```

2. **Create a virtual environment and activate it:**
    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # Linux/Mac
    source venv/bin/activate
    ```

3. **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4. **Run the application:**
    ```bash
    python app.py
    ```

5. **Open your browser:**
    ```
    http://127.0.0.1:5000
    ```

---

## 🗂️ Project Structure

```
Digital-Facial-Recognisation-Attendance-System/
├─ app.py                  # Main Flask application
├─ requirements.txt        # Project dependencies
├─ .gitignore              # Git ignore rules
├─ static/                 # CSS, JS, images
├─ templates/              # HTML templates
├─ models/                 # Trained ML models
├─ data/                   # Captured images or datasets
└─ README.md
```

---

## ⚙️ Usage

1. Admin/Teacher logs in to the dashboard.
2. Upload images or use a camera feed for real-time recognition.
3. Attendance is automatically marked in the database.
4. LCD and buzzer simulation messages are printed to the terminal.
5. View reports and statistics from the dashboard.

---

## 🔒 Security & Accuracy

- Prevents duplicate attendance for the same day
- Uses AI-powered face embeddings for accurate recognition
- Works with masks and varied lighting conditions

---

## 📄 License

This project is licensed under the MIT License. See the LICENSE file for details.

---

## 🙌 Acknowledgments

- OpenCV, Mediapipe, and scikit-learn communities
- Flask framework for web dashboard support
- Face recognition algorithms and online tutorials