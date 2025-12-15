# hardware.py
# ==========================
# SIMULATED HARDWARE OUTPUT
# ==========================

def attendance_success(name, confidence):
    print(f"[LCD] {name} Marked Today")
    print(f"[BUZZER] Beep (short)")
    print(f"[INFO] Confidence: {confidence:.2f}")

def attendance_duplicate(name):
    print(f"[LCD] {name} Already Marked Today")
    print("[BUZZER] Beep Beep (duplicate)")

def attendance_unknown():
    print("[LCD] Unknown Face")
    print("[BUZZER] Long Beep")
    print("[LCD] Please Register")  