import os
import numpy as np
import pickle
from model import train_model_background

def progress(pct, msg):
    print(f"PROGRESS: {pct}% - {msg}")

dataset_dir = 'dataset'

if not os.path.exists(dataset_dir):
    print("Error: No dataset folder found!")
else:
    print("Starting manual training...")
    train_model_background(dataset_dir, progress_callback=progress)
    print("\nTraining Complete! You can now restart run_pi.py")