import os
import numpy as np
import pickle
import sys
from model import train_model_background

def progress(pct, msg):
    """
    Callback function to show training progress in the terminal.
    """
    sys.stdout.write(f"\r[TRAINING] {pct}% - {msg}...")
    sys.stdout.flush()

def run_manual_fix():
    dataset_dir = 'dataset'

    # 1. Validation: Ensure dataset exists and isn't empty
    if not os.path.exists(dataset_dir):
        print(f"❌ Error: The folder '{dataset_dir}' does not exist.")
        return

    # Count subdirectories (students)
    student_folders = [f for f in os.listdir(dataset_dir) if os.path.isdir(os.path.join(dataset_dir, f))]
    
    if len(student_folders) == 0:
        print("❌ Error: No student folders found in 'dataset/'. Cannot train on empty data.")
        return

    print(f"✅ Found {len(student_folders)} student(s): {', '.join(student_folders)}")
    print("🚀 Starting AI Model Retraining (this may take a few minutes)...")
    print("-" * 50)

    try:
        # 2. Trigger the training logic from model.py
        # This will regenerate embeddings.pickle and le.pickle
        train_model_background(dataset_dir, progress_callback=progress)
        
        print("\n" + "-" * 50)
        print("✨ SUCCESS: AI Model has been updated with new student data.")
        print("👉 Action: You may now restart 'run_pi.py' to begin recognition.")
        
    except Exception as e:
        print(f"\n❌ Training Failed: {str(e)}")

if __name__ == "__main__":
    run_manual_fix()