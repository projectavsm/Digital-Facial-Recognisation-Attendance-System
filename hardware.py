# hardware.py
"""
Pi-Safe Hardware Abstraction Layer with Self-Healing I2C Logic
"""

import os
import time
import platform

# =========================================================
# ENVIRONMENT DETECTION
# =========================================================

def is_raspberry_pi() -> bool:
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
# HARDWARE INITIALIZATION & RECOVERY
# =========================================================

lcd = None
GPIO = None
BUZZER_PIN = 18

def init_lcd():
    """
    Attempts to initialize or reset the I2C LCD
    """
    if not IS_PI:
        return None
    try:
        from RPLCD.i2c import CharLCD
        new_lcd = CharLCD(
            i2c_expander="PCF8574",
            address=0x27,
            port=1,
            cols=16,
            rows=2,
            dotsize=8
        )
        new_lcd.clear()
        return new_lcd
    except Exception as e:
        print(f"[HARDWARE ERROR] LCD Init Failed: {e}")
        return None

if IS_PI:
    try:
        import RPi.GPIO as GPIO
        # Initial LCD setup
        lcd = init_lcd()
        
        # Buzzer setup
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUZZER_PIN, GPIO.OUT)
        GPIO.output(BUZZER_PIN, GPIO.LOW)
        print("[HARDWARE] Raspberry Pi hardware initialized with Self-Healing LCD")
    except Exception as e:
        print(f"[HARDWARE ERROR] Initial setup failed: {e}")
        IS_PI = False

# =========================================================
# SMART OUTPUT FUNCTIONS (SELF-HEALING)
# =========================================================

def lcd_display(line1: str = "", line2: str = ""):
    """
    Display text with automatic I2C recovery if garbage/errors occur
    """
    global lcd
    l1 = (line1 or "")[:16]
    l2 = (line2 or "")[:16]

    if IS_PI:
        try:
            if not lcd:
                lcd = init_lcd()
            
            if lcd:
                lcd.clear()
                lcd.write_string(l1)
                lcd.cursor_pos = (1, 0)
                lcd.write_string(l2)
        except Exception as e:
            print(f"[LCD I2C ERROR] {e}. Attempting hardware reset...")
            time.sleep(0.1) # Brief pause for bus stabilization
            lcd = init_lcd() # Recovery attempt
            if lcd:
                try:
                    lcd.write_string(l1)
                except:
                    pass
    else:
        # Laptop/Terminal Fallback
        output = f"[LCD] {l1}"
        if l2: output += f" | {l2}"
        print(output)


def buzzer_beep(times: int = 1, duration: float = 0.2):
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
# HIGH-LEVEL PUBLIC API
# =========================================================

def attendance_success(name: str, confidence: float | None = None):
    lcd_display(name, "Attendance OK")
    buzzer_beep(1)
    conf_str = f" ({confidence:.2f})" if confidence is not None else ""
    print(f"[SUCCESS] {name}{conf_str}")

def attendance_duplicate(name: str):
    lcd_display(name, "Already Marked")
    buzzer_beep(2)
    print(f"[DUPLICATE] {name} already marked today")

def attendance_unknown():
    lcd_display("Unknown Face", "Try Again")
    buzzer_beep(3)
    print("[UNKNOWN] Face not recognized")

def system_message(line1: str, line2: str = ""):
    lcd_display(line1, line2)

# =========================================================
# CLEANUP
# =========================================================

def cleanup():
    if IS_PI:
        try:
            if lcd:
                lcd.clear()
            if GPIO:
                GPIO.cleanup()
            print("[HARDWARE] Clean shutdown completed")
        except:
            pass