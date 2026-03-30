import os
import numpy as np
import pickle
import sys
import datetime
import mlflow
import mlflow.sklearn
from model import train_model_background

# 1. MLflow Configuration (Matched to your PuTTY port 5050)
mlflow.set_tracking_uri("http://localhost:5050") 
mlflow.set_experiment("Pi_Attendance_System") 

def progress(pct, msg):
    sys.stdout.write(f"\r[TRAINING] {pct}% - {msg}...")
    sys.stdout.flush()

def run_manual_fix():
    dataset_dir = 'dataset'

    if not os.path.exists(dataset_dir):
        print(f"❌ Error: The folder '{dataset_dir}' does not exist.")
        return

    student_folders = [f for f in os.listdir(dataset_dir) if os.path.isdir(os.path.join(dataset_dir, f))]
    
    if len(student_folders) == 0:
        print("❌ Error: No student folders found.")
        return

    # Metadata for MLflow
    total_images = sum([len(os.listdir(os.path.join(dataset_dir, f))) for f in student_folders])

    print(f"✅ Found {len(student_folders)} student(s) | {total_images} total images.")
    print("🚀 Starting AI Model Retraining with MLflow Tracking...")
    print("-" * 50)

    # 2. THE MLFLOW "RECORD" BLOCK
    # This creates a unique entry in your dashboard
    with mlflow.start_run(run_name=f"Manual_Fix_{datetime.datetime.now().strftime('%H:%M:%S')}"):
        
        # Log the "Ingredients" (Parameters)
        mlflow.log_param("student_count", len(student_folders))
        mlflow.log_param("image_count", total_images)
        mlflow.set_tag("trained_by", "manual_script")

        try:
            # 3. Trigger the training
            train_model_background(dataset_dir, progress_callback=progress)
            
            # 4. Log the "Result" (Artifacts)
            # This saves a copy of the model inside MLflow so you can't lose it
            if os.path.exists("model.pkl"):
                mlflow.log_artifact("model.pkl")
            if os.path.exists("le.pickle"):
                mlflow.log_artifact("le.pickle")
            
            print("\n" + "-" * 50)
            print("✨ SUCCESS: AI Model updated and logged to http://localhost:5050")
            
        except Exception as e:
            mlflow.log_param("error", str(e))
            print(f"\n❌ Training Failed: {str(e)}")

if __name__ == "__main__":
    run_manual_fix()