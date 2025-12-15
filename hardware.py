# hardware.py
"""
Pi-Safe Hardware Abstraction Layer

Laptop:
    - Prints LCD + buzzer output to terminal

Raspberry Pi:
    - Uses 16x2 I2C LCD
    - Uses GPIO buzzer

This file MUST NEVER crash the system.
"""

import os
import time
import platform

# =========================================================
# ENVIRONMENT DETECTION
# =========================================================

def is_raspberry_pi() -> bool:
    """
    Robust Raspberry Pi detection
    """
    try:
        if platform.system() != "Linux":
            return False

        model_path = "/proc/device-tree/model"
        if os.path.exists(model_path):
            with open(model_path, "r") as f:
                return "raspberry pi" in f.read().lower()

        return False
    except Exception:
        return False


IS_PI = is_raspberry_pi()

# =========================================================
# HARDWARE INITIALIZATION (PI ONLY)
# =========================================================

lcd = None
GPIO = None
BUZZER_PIN = 18

if IS_PI:
    try:
        import RPi.GPIO as GPIO
        from RPLCD.i2c import CharLCD

        # ---- LCD CONFIG ----
        lcd = CharLCD(
            i2c_expander="PCF8574",
            address=0x27,   # common I2C address
            port=1,
            cols=16,
            rows=2,
            dotsize=8
        )

        # ---- BUZZER CONFIG ----
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUZZER_PIN, GPIO.OUT)
        GPIO.output(BUZZER_PIN, GPIO.LOW)

        print("[HARDWARE] Raspberry Pi hardware initialized")

    except Exception as e:
        print("[HARDWARE ERROR] Pi hardware failed, fallback to terminal mode")
        print("Reason:", e)
        IS_PI = False
        lcd = None
        GPIO = None

else:
    print("[HARDWARE] Running in Laptop / Terminal mode")

# =========================================================
# LOW-LEVEL OUTPUT FUNCTIONS
# =========================================================

def lcd_display(line1: str = "", line2: str = ""):
    """
    Display text on LCD or terminal
    """
    line1 = (line1 or "")[:16]
    line2 = (line2 or "")[:16]

    if IS_PI and lcd:
        try:
            lcd.clear()
            lcd.write_string(line1)
            if line2:
                lcd.cursor_pos = (1, 0)
                lcd.write_string(line2)
        except Exception as e:
            print("[LCD ERROR]", e)
    else:
        if line2:
            print(f"[LCD] {line1} | {line2}")
        else:
            print(f"[LCD] {line1}")


def buzzer_beep(times: int = 1, duration: float = 0.2):
    """
    Beep buzzer or print to terminal
    """
    if IS_PI and GPIO:
        try:
            for _ in range(times):
                GPIO.output(BUZZER_PIN, GPIO.HIGH)
                time.sleep(duration)
                GPIO.output(BUZZER_PIN, GPIO.LOW)
                time.sleep(0.1)
        except Exception as e:
            print("[BUZZER ERROR]", e)
    else:
        print("[BUZZER]", "Beep " * times)

# =========================================================
# HIGH-LEVEL PUBLIC API (USED BY SYSTEM)
# =========================================================

def attendance_success(name: str, confidence: float | None = None):
    """
    Attendance marked successfully
    """
    lcd_display(name, "Attendance OK")
    buzzer_beep(1)

    if confidence is not None:
        print(f"[SUCCESS] {name} ({confidence:.2f})")
    else:
        print(f"[SUCCESS] {name}")


def attendance_duplicate(name: str):
    """
    Attendance already marked today
    """
    lcd_display(name, "Already Marked")
    buzzer_beep(2)
    print(f"[DUPLICATE] {name} already marked today")


def attendance_unknown():
    """
    Face not recognized
    """
    lcd_display("Unknown Face", "")
    buzzer_beep(3)
    print("[UNKNOWN] Face not recognized")


def system_message(line1: str, line2: str = ""):
    """
    Generic system status message
    """
    lcd_display(line1, line2)


# =========================================================
# CLEANUP (IMPORTANT FOR SYSTEMD)
# =========================================================

def cleanup():
    """
    Cleanup GPIO & LCD safely
    """
    if IS_PI:
        try:
            if lcd:
                lcd.clear()
            if GPIO:
                GPIO.cleanup()
            print("[HARDWARE] Clean shutdown completed")
        except Exception:
            pass
