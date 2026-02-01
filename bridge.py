import subprocess
import re
import smtplib
import time
import sys
import os
from email.message import EmailMessage
from dotenv import load_dotenv  

# Load environment variables from .env file
load_dotenv()

# CONFIGURATION
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

def send_email(url):

    if not all([GMAIL_USER, GMAIL_APP_PASS, RECIPIENT_EMAIL]):
        print("❌ Error: Missing credentials in .env file!")
        return
    msg = EmailMessage()
    msg.set_content(f"The Attendance System is online!\n\nAccess Link: {url}\n\nTime: {time.ctime()}")
    msg['Subject'] = 'Pi System - New Live Link'
    msg['From'] = GMAIL_USER
    msg['To'] = RECIPIENT_EMAIL

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASS)
            smtp.send_message(msg)
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def start_bridge():
    print("🚀 Starting Cloudflare Tunnel...")
    # We use stderr=subprocess.STDOUT because cloudflared logs to stderr
    proc = subprocess.Popen(
        ['cloudflared', 'tunnel', '--url', 'http://localhost:5000'], 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True
    )

    url_found = False
    
    # Read output line by line
    try:
        for line in iter(proc.stdout.readline, ''):
            # Print logs to console so we can see what's happening
            sys.stdout.write(line) 
            
            if not url_found:
                match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if match:
                    url = match.group(0)
                    print(f"\n✨ FOUND URL: {url}")
                    send_email(url)
                    url_found = True
                    print("🔗 Bridge active. Leave this terminal open.\n")
    except KeyboardInterrupt:
        print("\nStopping Bridge...")
        proc.terminate()

if __name__ == "__main__":
    start_bridge()