import os
import cv2
import csv
import urllib.request
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import train_model

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (9, 10), (10, 11), (11, 12),
    (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17)
]

def calculate_orientation(landmarks, aspect_ratio):
    if not landmarks or len(landmarks) < 21:
        return 0.0, 0.0
        
    # Scale X by aspect_ratio
    wrist = np.array([landmarks[0].get('x', 0.0) * aspect_ratio, landmarks[0].get('y', 0.0), landmarks[0].get('z', 0.0)])
    index_mcp = np.array([landmarks[5].get('x', 0.0) * aspect_ratio, landmarks[5].get('y', 0.0), landmarks[5].get('z', 0.0)])
    pinky_mcp = np.array([landmarks[17].get('x', 0.0) * aspect_ratio, landmarks[17].get('y', 0.0), landmarks[17].get('z', 0.0)])
    thumb_mcp = np.array([landmarks[2].get('x', 0.0) * aspect_ratio, landmarks[2].get('y', 0.0), landmarks[2].get('z', 0.0)])
    
    v1 = index_mcp - wrist
    v2 = pinky_mcp - wrist
    
    normal = np.cross(v1, v2)
    z_component = normal[2]
    
    thumb_is_left = thumb_mcp[0] < pinky_mcp[0]
    is_palm = 1.0 if z_component > 0 else 0.0
    is_left = 1.0 if thumb_is_left == (is_palm == 0.0) else 0.0
    
    if is_left:
        z_component = -z_component
        
    is_palm_facing = 1.0 if z_component > 0 else 0.0
    return is_palm_facing, is_left

def normalize_landmarks(landmarks, aspect_ratio):
    if not landmarks or len(landmarks) != 21:
        return [0.0] * 63
        
    coords = []
    for lm in landmarks:
        coords.extend([lm.get('x', 0.0) * aspect_ratio, lm.get('y', 0.0), lm.get('z', 0.0)])
        
    coords = np.array(coords, dtype=np.float32)
    
    wrist = coords[:3].copy()
    for i in range(21):
        coords[i*3 : i*3+3] -= wrist
        
    middle_mcp = coords[9*3 : 9*3+3]
    hand_size = np.linalg.norm(middle_mcp)
    
    if hand_size > 0.001:
        coords /= hand_size
        
    return coords.tolist()

def process_dataset():
    data_dir = '../data'
    if not os.path.exists(data_dir):
        data_dir = 'data' # fallback if run from root
        if not os.path.exists(data_dir):
            print("[-] Error: 'data' folder not found. Please place it in the workspace root.")
            return

    model_path = 'hand_landmarker.task'
    dataset_path = 'dataset.csv'
    
    # Download hand landmarker task file if missing
    if not os.path.exists(model_path):
        print("[*] 'hand_landmarker.task' model file not found.")
        print("[*] Downloading model from Google MediaPipe Repository...")
        try:
            url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
            urllib.request.urlretrieve(url, model_path)
            print("[+] Model downloaded successfully.")
        except Exception as e:
            print(f"[-] Failed to download model: {e}")
            return
            
    print("\n[*] Initializing MediaPipe Vision HandLandmarker...")
    try:
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_hands=1
        )
        detector = vision.HandLandmarker.create_from_options(options)
        print("[+] MediaPipe landmarker initialized.")
    except Exception as e:
        print(f"[-] Failed to initialize MediaPipe landmarker: {e}")
        return

    # Clear/create dataset.csv
    try:
        with open(dataset_path, 'w', newline='') as f:
            pass # clear file
        print(f"[+] Initialized '{dataset_path}'")
    except Exception as e:
        print(f"[-] Failed to create/clear dataset.csv: {e}")
        return

    subdirs = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))]
    subdirs.sort()
    
    total_processed = 0
    total_success = 0
    
    print(f"\n[*] Scanning '{data_dir}' folders: {subdirs}")
    for label in subdirs:
        class_dir = os.path.join(data_dir, label)
        image_files = [f for f in os.listdir(class_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        print(f"  Processing class '{label}' ({len(image_files)} images)...")
        
        class_success = 0
        for img_file in image_files:
            img_path = os.path.join(class_dir, img_file)
            image = cv2.imread(img_path)
            if image is None:
                continue
                
            total_processed += 1
            h, w, c = image.shape
            aspect_ratio = w / h
            
            # Convert BGR to RGB and process
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
            results = detector.detect(mp_image)
            
            if results.hand_landmarks:
                hand_landmarks = results.hand_landmarks[0]
                
                # Mirror X-coordinates (1.0 - x) to align with client mirrored coordinate space
                landmarks_list = [{"x": 1.0 - lm.x, "y": lm.y, "z": lm.z} for lm in hand_landmarks]
                
                is_palm, is_left = calculate_orientation(landmarks_list, aspect_ratio)
                normalized = normalize_landmarks(landmarks_list, aspect_ratio)
                
                # Build 130-feature vector
                features = [0.0] * 130
                features[0:63] = normalized
                features[126] = is_palm
                features[127] = is_left
                features[128] = -1.0
                features[129] = -1.0
                
                with open(dataset_path, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(features + [label])
                    
                class_success += 1
                total_success += 1
                
        print(f"  [+] Class '{label}' finished: {class_success}/{len(image_files)} hands successfully extracted.")
        
    print(f"\n[+] Landmark extraction complete: {total_success}/{total_processed} images parsed.")
    print("----------------------------------------------------")
    print("[*] Starting offline model retraining...")
    train_model.train()

if __name__ == '__main__':
    process_dataset()
