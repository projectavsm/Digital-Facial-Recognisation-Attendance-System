# model.py 
import os
import cv2
import numpy as np
import pickle
import json
import mlflow
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

# --- FILE PATHS & CONSTANTS ---
# Using absolute paths where possible to ensure background threads find the files
APP_DIR = os.path.dirname(os.path.abspath(__file__))
TRAIN_STATUS_FILE = os.path.join(APP_DIR, "train_status.json")
MODEL_PATH = os.path.join(APP_DIR, "model.pkl")

# -------------------------------
# Helper: Status Sync
# -------------------------------
def write_final_status(data):
    """
    Updates the JSON file to signal the frontend that training 
    is no longer running.
    """
    with open(TRAIN_STATUS_FILE, "w") as f:
        json.dump(data, f)

# -------------------------------
# Utility: Image Processing
# -------------------------------
def crop_face_and_embed(bgr_image, detection):
    """
    Crops the face from a BGR image using MediaPipe detections 
    and converts it to a 32x32 grayscale normalized vector.
    """
    h, w = bgr_image.shape[:2]

    # Extract bounding box relative coordinates
    bbox = detection.location_data.relative_bounding_box
    x1 = int(max(0, bbox.xmin * w))
    y1 = int(max(0, bbox.ymin * h))
    x2 = int(min(w, (bbox.xmin + bbox.width) * w))
    y2 = int(min(h, (bbox.ymin + bbox.height) * h))

    if x2 <= x1 or y2 <= y1:
        return None

    # Crop, grayscale, and resize
    face = bgr_image[y1:y2, x1:x2]
    face = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    face = cv2.resize(face, (32, 32), interpolation=cv2.INTER_AREA)

    # Flatten and normalize (0.0 to 1.0)
    return face.flatten().astype(np.float32) / 255.0

def extract_embedding_for_image(stream_or_bytes):
    """
    Takes a Flask file stream, detects the face, and returns the embedding.
    Used during enrollment and single-image testing.
    """
    import mediapipe as mp
    mp_face = mp.solutions.face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=0.5
    )

    # Decode image from stream
    data = stream_or_bytes.read()
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    
    if img is None:
        return None

    # Process face detection
    results = mp_face.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if not results.detections:
        return None

    return crop_face_and_embed(img, results.detections[0])

# -------------------------------
# Model Loading & Prediction
# -------------------------------
def load_model_if_exists():
    """Returns the loaded pickle model or None if not trained yet."""
    if not os.path.exists(MODEL_PATH):
        return None
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)

def predict_with_model(clf, emb):
    """Predicts user_id and confidence score from an embedding."""
    proba = clf.predict_proba([emb])[0]
    idx = np.argmax(proba)
    return clf.classes_[idx], float(proba[idx])

# -------------------------------
# Main Training Logic
# -------------------------------
def train_model_background(dataset_dir, progress_callback=None):
    """
    Background task to scan dataset, extract embeddings, 
    train RandomForest, and update the global status file.
    """
    import mediapipe as mp
    mp_face = mp.solutions.face_detection.FaceDetection(
        model_selection=0, min_detection_confidence=0.3
    )

    X, y = [], []

    # Get student folders (each folder name is a user_id)
    student_dirs = [d for d in os.listdir(dataset_dir) if os.path.isdir(os.path.join(dataset_dir, d))]
    total_students = max(1, len(student_dirs))
    processed = 0

    for user_id in student_dirs:
        folder = os.path.join(dataset_dir, user_id)
        files = [f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png"))]

        for fn in files:
            img = cv2.imread(os.path.join(folder, fn))
            if img is None: continue

            results = mp_face.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            if not results.detections: continue

            # Extract feature vector
            emb = crop_face_and_embed(img, results.detections[0])
            if emb is not None:
                X.append(emb)
                y.append(user_id)

        processed += 1
        if progress_callback:
            # Scale 0-80% for image processing phase
            pct = int((processed / total_students) * 80)
            progress_callback(pct, f"Processing Student {processed}/{total_students}...")

    # Guard clause: No data
    if len(X) == 0:
        if progress_callback: progress_callback(0, "Error: No face data found")
        write_final_status({"running": False, "progress": 0, "message": "Failed: No Images"})
        return

    # Convert to arrays for Scikit-Learn
    X = np.stack(X)
    y = np.array(y)

    if progress_callback:
        progress_callback(85, "Training AI Model...")

    # Initialize and train classifier
    clf = RandomForestClassifier(n_estimators=150, n_jobs=-1, random_state=42)
    clf.fit(X, y)

    # Calculate metrics
    predictions = clf.predict(X)
    train_acc = accuracy_score(y, predictions)

    # Log to MLflow if an experiment is active
    if mlflow.active_run():
        mlflow.log_metric("train_accuracy", float(train_acc))
        mlflow.log_param("n_estimators", 150)
        print(f"MLflow Logged: Accuracy {train_acc:.2%}")

    # Save trained model to disk
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(clf, f)

    # --- CRITICAL: Update Status to Idle ---
    if progress_callback:
        progress_callback(100, "Finalizing...")
    
    write_final_status({
        "running": False,
        "progress": 100,
        "message": f"Complete! Accuracy: {train_acc:.2%}"
    })
    print("✅ Training Finished: Model saved and status file updated.")