import os
import cv2
import pickle
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# Load the built-in OpenCV Haar Cascade detector
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

dataset_dir = 'dataset'
X, y = [], []

def get_embedding(img):
    # 1. Convert to grayscale for Haar Cascade
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 2. Increase contrast (Histogram Equalization)
    gray = cv2.equalizeHist(gray)
    
    # 3. Detect faces
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    
    if len(faces) > 0:
        # Take the largest face found
        (x, y_pos, w, h) = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)[0]
        
        # Crop and resize
        face_img = gray[y_pos:y_pos+h, x:x+w]
        face_img = cv2.resize(face_img, (32, 32))
        return face_img.flatten()
    return None

print("--- Starting Haar Cascade Training ---")

for user_id in os.listdir(dataset_dir):
    folder = os.path.join(dataset_dir, user_id)
    if not os.path.isdir(folder): continue
    
    print(f"Processing {user_id}...")
    count = 0
    for fn in os.listdir(folder):
        if not fn.lower().endswith(('.jpg', '.jpeg', '.png')): continue
        img = cv2.imread(os.path.join(folder, fn))
        if img is None: continue
        
        # In Haar Cascades, rotation usually isn't the problem, but we try 0 and 180
        for angle in [0, 180]:
            rotated = img if angle == 0 else cv2.rotate(img, cv2.ROTATE_180)
            emb = get_embedding(rotated)
            if emb is not None:
                X.append(emb)
                y.append(user_id)
                count += 1
                break
    print(f"  -> Successfully extracted {count} faces.")

if len(X) > 0:
    print(f"Training RandomForest on {len(X)} samples...")
    clf = RandomForestClassifier(n_estimators=100)
    clf.fit(X, y)
    with open("model.pkl", "wb") as f:
        pickle.dump(clf, f)
    print("\nSUCCESS! model.pkl created.")
else:
    print("\nFAILED: Even Haar Cascade could not find a face. Please take photos with a light in front of your face.")