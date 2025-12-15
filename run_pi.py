# run_pi.py
"""
Headless Raspberry Pi Attendance System
---------------------------------------
- Auto-start Flask API (optional)
- Continuous camera + recognition loop
- LCD + buzzer only
- No frontend required
"""

import threading
import time
import signal
import sys

from app import app                   # Your Flask app
from hardware import (
    attendance_success,
    attendance_duplicate,
    attendance_unknown,
    system_message,
    cleanup
)
from model import recognize_face      # Your face recognition logic

running = True

# ---------------------------------------------------------
# CAMERA LOOP
# ---------------------------------------------------------
def camera_loop():
    """
    Continuous camera + recognition loop
    """
    system_message("System Ready", "Scanning faces")

    while running:
        try:
            result = recognize_face()  # returns (name, status) or None
            if result is None:
                time.sleep(0.5)
                continue

            name, status = result

            if status == "duplicate":
                attendance_duplicate(name)

            elif status == "marked":
                attendance_success(name)

            elif status == "unknown":
                attendance_unknown()

            time.sleep(2)  # short pause to prevent spamming

        except Exception as e:
            system_message("Camera Error", "")
            print("[ERROR]", e)
            time.sleep(2)

# ---------------------------------------------------------
# SHUTDOWN HANDLER
# ---------------------------------------------------------
def shutdown_handler(signum, frame):
    global running
    running = False
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == "__main__":
    print("[PI] Starting headless attendance system...")

    # Start camera loop in background
    threading.Thread(target=camera_loop, daemon=True).start()

    # Start Flask API for optional access
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )
