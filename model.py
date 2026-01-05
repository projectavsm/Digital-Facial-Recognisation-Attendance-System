#model.py 
import os
import cv2
import numpy as np
import pickle
from sklearn.ensemble import RandomForestClassifier

# -------------------------------
# Paths and constants
# -------------------------------
MODEL_PATH = "model.pkl"  # file where trained RandomForest model is saved

# -------------------------------
# Utility: Crop face and extract embedding
# -------------------------------
def crop_face_and_embed(bgr_image, detection):
    """
    Crops the face from a BGR image and converts it to a small grayscale vector (embedding)
    """
    h, w = bgr_image.shape[:2]

    # Get bounding box relative coordinates from Mediapipe detection
    bbox = detection.location_data.relative_bounding_box
    x1 = int(max(0, bbox.xmin * w))
    y1 = int(max(0, bbox.ymin * h))
    x2 = int(min(w, (bbox.xmin + bbox.width) * w))
    y2 = int(min(h, (bbox.ymin + bbox.height) * h))

    # Check for invalid bbox
    if x2 <= x1 or y2 <= y1:
        return None

    # Crop face region
    face = bgr_image[y1:y2, x1:x2]

    # Convert to grayscale and resize to fixed size
    face = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    face = cv2.resize(face, (32,32), interpolation=cv2.INTER_AREA)

    # Flatten to vector and normalize
    emb = face.flatten().astype(np.float32) / 255.0
    return emb

# -------------------------------
# Extract embedding from uploaded image stream
# -------------------------------
def extract_embedding_for_image(stream_or_bytes):
    """
    Accepts a file-like object (Flask file stream) and returns a face embedding vector
    """
    import mediapipe as mp
    mp_face = mp.solutions.face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=0.5
    )

    # Read image from stream into BGR numpy array
    data = stream_or_bytes.read()
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    # Detect face
    results = mp_face.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if not results.detections:
        return None

    # Extract embedding
    emb = crop_face_and_embed(img, results.detections[0])
    return emb

# -------------------------------
# Load existing model from disk
# -------------------------------
def load_model_if_exists():
    """
    Loads the trained RandomForest model if it exists
    """
    if not os.path.exists(MODEL_PATH):
        return None
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)

# -------------------------------
# Predict student using model
# -------------------------------
def predict_with_model(clf, emb):
    """
    Returns predicted user_id (string) and confidence
    """
    proba = clf.predict_proba([emb])[0]
    idx = np.argmax(proba)
    label = clf.classes_[idx]  # now label is string user_id
    conf = float(proba[idx])
    return label, conf

# -------------------------------
# Background training function
# -------------------------------
def train_model_background(dataset_dir, progress_callback=None):
    """
    Trains a RandomForest classifier on all student images in dataset_dir
    Each student folder must be named after user_id (string from MySQL)
    Progress callback optional: progress_callback(percent, message)
    """
    import mediapipe as mp
    mp_face = mp.solutions.face_detection.FaceDetection(
        model_selection=0, min_detection_confidence=0.3
    )

    X = []  # embeddings
    y = []  # labels (user_id strings)

    # List all student folders (folder names = user_id)
    student_dirs = [d for d in os.listdir(dataset_dir) if os.path.isdir(os.path.join(dataset_dir, d))]
    total_students = max(1, len(student_dirs))
    processed = 0

    # Iterate over each student
    for user_id in student_dirs:
        folder = os.path.join(dataset_dir, user_id)
        files = [f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png"))]

        # Process each image
        for fn in files:
            path = os.path.join(folder, fn)
            img = cv2.imread(path)
            if img is None:
                continue

            results = mp_face.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            if not results.detections:
                continue

            emb = crop_face_and_embed(img, results.detections[0])
            if emb is None:
                continue

            # Add to training data
            X.append(emb)
            y.append(user_id)  # now storing string user_id instead of int

        processed += 1
        if progress_callback:
            pct = int((processed / total_students) * 80)  # up to 80% for feature extraction
            progress_callback(pct, f"Processed {processed}/{total_students} students")

    # Check if we have any training data
    if len(X) == 0:
        if progress_callback:
            progress_callback(0, "No training data found")
        return

    # Convert to numpy arrays
    X = np.stack(X)
    y = np.array(y)

    # Train RandomForest
    if progress_callback:
        progress_callback(85, "Training RandomForest classifier...")
    clf = RandomForestClassifier(n_estimators=150, n_jobs=-1, random_state=42)
    clf.fit(X, y)

    # Save model
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(clf, f)

    if progress_callback:
        progress_callback(100, "Training complete")
