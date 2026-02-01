import subprocess
import time
import sys

def launch():
    print("🔔 Starting Attendance System Master Launcher...")
    
    try:
        # 1. Start the Main AI/Web Server
        # We use sys.executable to ensure it uses the same Python environment
        app_proc = subprocess.Popen([sys.executable, 'run_pi.py'])
        print("✅ Main AI System started.")

        # Give the Flask server 2 seconds to warm up
        time.sleep(2)

        # 2. Start the Bridge (Cloudflare + Email)
        bridge_proc = subprocess.Popen([sys.executable, 'bridge.py'])
        print("✅ Cloudflare Bridge started.")

        print("\n🚀 SYSTEM ONLINE. Check your email for the link in a few seconds.")
        print("Press Ctrl+C to shut down all components.\n")

        # Keep the script running while the processes are alive
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Shutting down system...")
        bridge_proc.terminate()
        app_proc.terminate()
        print("👋 All processes closed safely.")

if __name__ == "__main__":
    launch()