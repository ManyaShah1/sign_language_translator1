import os
import sys
import subprocess
import shutil
import zipfile
import urllib.request

# 1. Auto-install dependencies
required_packages = ["numpy", "opencv-python", "mediapipe", "pandas", "huggingface_hub"]
for package in required_packages:
    import_name = "cv2" if package == "opencv-python" else package
    try:
        __import__(import_name)
    except ImportError:
        print(f"[!] Installing missing dependency: {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

import cv2
import numpy as np
import mediapipe as mp
import pandas as pd
from huggingface_hub import get_token, hf_hub_download
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Target vocabulary
TARGET_TOKENS = [
    "HELLO", "START", "CHECKUP", "CHECK", "BLOOD_PRESSURE", "PAIN", 
    "CHEST", "DIZZY", "WEAK", "SEVERE", "CONNECT", "DOCTOR", 
    "ONLINE", "PRINT", "REPORT",
    "THANKYOU", "YOU", "I", "MOTHER", "FATHER"
]

DATA_DIR = "data_sequences"
TARGET_FRAMES = 45
FEATURE_DIM = 138  # 4 pose joints * 3 + 2 hands * 21 landmarks * 3 = 138 features

def interpolate_sequence(sequence, target_len=45):
    """
    Interpolates or truncates a sequence of shape (L, 138) to target_len (45, 138).
    """
    curr_len = len(sequence)
    if curr_len == 0:
        return np.zeros((target_len, FEATURE_DIM), dtype=np.float32)
        
    if curr_len == target_len:
        return np.array(sequence, dtype=np.float32)
        
    sequence = np.array(sequence, dtype=np.float32)
    new_indices = np.linspace(0, curr_len - 1, target_len)
    interpolated = np.zeros((target_len, FEATURE_DIM), dtype=np.float32)
    
    for i in range(FEATURE_DIM):
        interpolated[:, i] = np.interp(new_indices, np.arange(curr_len), sequence[:, i])
        
    return interpolated

def generate_synthetic_samples_for_word(word, start_idx, num_samples):
    """
    Generates synthetic landmark sequence curves for a single word
    to reach the desired number of samples.
    """
    print(f"[*] Generating {num_samples} synthetic samples for '{word}' starting at index {start_idx}...")
    np.random.seed(42 + hash(word) % 1000)
    
    word_dir = os.path.join(DATA_DIR, word)
    os.makedirs(word_dir, exist_ok=True)
    
    for s in range(start_idx, start_idx + num_samples):
        seq = []
        base_phase = np.random.uniform(0, 2 * np.pi)
        for f in range(TARGET_FRAMES):
            t = f / TARGET_FRAMES
            # Sinusoidal motion signature for each word to distinguish them
            motion = 0.1 * np.sin(2 * np.pi * t + base_phase + hash(word) % 5)
            
            frame = []
            # Left Shoulder
            frame.extend([-0.2, 0.0, 0.0])
            # Right Shoulder
            frame.extend([0.2, 0.0, 0.0])
            # Left Elbow
            frame.extend([-0.3 + motion, 0.2, 0.0])
            # Right Elbow
            frame.extend([0.3 - motion, 0.2, 0.0])
            
            # Left Hand: 21 landmarks
            for lm in range(21):
                frame.extend([
                    -0.2 + (lm * 0.01 + motion) * np.cos(lm),
                    0.3 + (lm * 0.01 + motion) * np.sin(lm),
                    lm * -0.005 + np.random.normal(0, 0.001)
                ])
            # Right Hand: 21 landmarks
            for lm in range(21):
                frame.extend([
                    0.2 + (lm * 0.01 + motion) * np.cos(lm + 1),
                    0.3 + (lm * 0.01 + motion) * np.sin(lm + 1),
                    lm * -0.005 + np.random.normal(0, 0.001)
                ])
            seq.append(frame)
            
        seq_arr = np.array(seq, dtype=np.float32)
        np.save(os.path.join(word_dir, f"sample_{s}.npy"), seq_arr)

def main():
    print("====================================================")
    # Wipe directory contents as requested
    if os.path.exists(DATA_DIR):
        print(f"[*] Wiping existing directory '{DATA_DIR}'...")
        shutil.rmtree(DATA_DIR)
    os.makedirs(DATA_DIR, exist_ok=True)

    # Gated dataset check
    print("[*] Checking Hugging Face credentials for Exploration-Lab/CISLR...")
    token = get_token()
    
    if not token:
        print("[!] No Hugging Face token detected. Cannot download gated dataset.")
        print("[!] Falling back to generating synthetic data for all words.")
        for word in TARGET_TOKENS:
            generate_synthetic_samples_for_word(word, 0, 20)
        return

    # Download dataset CSV metadata
    print("[*] Downloading dataset metadata from Hugging Face...")
    try:
        dataset_csv_path = hf_hub_download(repo_id="Exploration-Lab/CISLR", filename="dataset.csv", repo_type="dataset")
        df_all = pd.read_csv(dataset_csv_path)
        print("[OK] Dataset CSV metadata loaded successfully.")
    except Exception as e:
        print(f"[-] Error loading CSV metadata: {e}")
        print("[!] Falling back to generating synthetic data for all words.")
        for word in TARGET_TOKENS:
            generate_synthetic_samples_for_word(word, 0, 20)
        return

    # Download main videos ZIP file
    print("[*] Downloading expert videos zip from Hugging Face. This is a ~1.1GB file...")
    try:
        zip_path = hf_hub_download(repo_id="Exploration-Lab/CISLR", filename="CISLR_v1.5-a_videos/CISLR_v1.5-a_videos.zip", repo_type="dataset")
        print(f"[OK] Video zip downloaded/cached at: {zip_path}")
    except Exception as e:
        print(f"[-] Error downloading videos zip: {e}")
        print("[!] Falling back to generating synthetic data for all words.")
        for word in TARGET_TOKENS:
            generate_synthetic_samples_for_word(word, 0, 20)
        return

    # Make sure pose landmarker task is downloaded
    pose_model_path = "pose_landmarker.task"
    if not os.path.exists(pose_model_path):
        print("[*] Downloading pose landmarker model asset...")
        pose_model_url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
        try:
            urllib.request.urlretrieve(pose_model_url, pose_model_path)
            print("[OK] Pose landmarker model asset downloaded.")
        except Exception as e:
            print(f"[-] Error downloading pose model: {e}")
            print("[!] Falling back to generating synthetic data for all words.")
            for word in TARGET_TOKENS:
                generate_synthetic_samples_for_word(word, 0, 20)
            return

    # Initialize MediaPipe Tasks API Landmarkers
    print("[*] Initializing MediaPipe Vision Landmarkers...")
    try:
        hand_options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path='hand_landmarker.task'),
            num_hands=2,
            running_mode=vision.RunningMode.IMAGE
        )
        pose_options = vision.PoseLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path='pose_landmarker.task'),
            running_mode=vision.RunningMode.IMAGE
        )
        hand_detector = vision.HandLandmarker.create_from_options(hand_options)
        pose_detector = vision.PoseLandmarker.create_from_options(pose_options)
        print("[OK] Landmarkers initialized successfully.")
    except Exception as e:
        print(f"[-] Error initializing landmarkers: {e}")
        print("[!] Falling back to generating synthetic data for all words.")
        for word in TARGET_TOKENS:
            generate_synthetic_samples_for_word(word, 0, 20)
        return

    # Open the ZIP archive
    print("[*] Extracting and processing videos...")
    counts = {w: 0 for w in TARGET_TOKENS}
    temp_dir = "temp_videos"
    os.makedirs(temp_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            all_files = z.namelist()
            # Filter and match target glosses
            df_targets = df_all[df_all['gloss'].astype(str).str.upper().str.replace(' ', '').isin(TARGET_TOKENS)].copy()
            df_targets['gloss_upper'] = df_targets['gloss'].astype(str).str.upper().str.replace(' ', '')
            
            print(f"[*] Found {len(df_targets)} matching entries in the metadata.")
            
            for index, row in df_targets.iterrows():
                gloss = row['gloss_upper']
                if counts[gloss] >= 20:
                    continue
                
                uid = row['uid']
                zip_filename = f"CISLR_v1.5-a_videos/{uid}.mp4"
                if zip_filename not in all_files:
                    matches = [f for f in all_files if f.endswith(f"{uid}.mp4")]
                    if matches:
                        zip_filename = matches[0]
                    else:
                        print(f"[-] Warning: Video for uid {uid} not found in zip archive.")
                        continue
                
                # Extract file to temp folder
                try:
                    extracted_path = z.extract(zip_filename, temp_dir)
                    video_file = extracted_path
                except Exception as zip_ex:
                    print(f"[-] Failed to extract zip member {zip_filename}: {zip_ex}")
                    continue

                # Process the video file
                print(f"[*] Processing '{gloss}' video: {uid}.mp4")
                cap = cv2.VideoCapture(video_file)
                sequence = []
                
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        break
                        
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                    
                    pose_results = pose_detector.detect(mp_image)
                    hand_results = hand_detector.detect(mp_image)
                    
                    pose_coords = [0.0] * 12
                    left_hand_coords = [0.0] * 63
                    right_hand_coords = [0.0] * 63
                    
                    anchor_x, anchor_y, anchor_z = 0.5, 0.5, 0.0
                    
                    if len(pose_results.pose_landmarks) > 0:
                        landmarks = pose_results.pose_landmarks[0]
                        left_shoulder = landmarks[11]
                        right_shoulder = landmarks[12]
                        left_elbow = landmarks[13]
                        right_elbow = landmarks[14]
                        
                        # Torso midpoint global origin (mirrored X)
                        anchor_x = ((1.0 - left_shoulder.x) + (1.0 - right_shoulder.x)) / 2.0
                        anchor_y = (left_shoulder.y + right_shoulder.y) / 2.0
                        anchor_z = (left_shoulder.z + right_shoulder.z) / 2.0
                        
                        # Left Shoulder
                        pose_coords[0:3] = [(1.0 - left_shoulder.x) - anchor_x, left_shoulder.y - anchor_y, left_shoulder.z - anchor_z]
                        # Right Shoulder
                        pose_coords[3:6] = [(1.0 - right_shoulder.x) - anchor_x, right_shoulder.y - anchor_y, right_shoulder.z - anchor_z]
                        # Left Elbow
                        pose_coords[6:9] = [(1.0 - left_elbow.x) - anchor_x, left_elbow.y - anchor_y, left_elbow.z - anchor_z]
                        # Right Elbow
                        pose_coords[9:12] = [(1.0 - right_elbow.x) - anchor_x, right_elbow.y - anchor_y, right_elbow.z - anchor_z]
                    
                    if len(hand_results.hand_landmarks) > 0:
                        for hand_idx, hand_lms in enumerate(hand_results.hand_landmarks):
                            label = hand_results.handedness[hand_idx][0].category_name
                            
                            hand_coords = []
                            for lm in hand_lms:
                                hand_coords.extend([(1.0 - lm.x) - anchor_x, lm.y - anchor_y, lm.z - anchor_z])
                                
                            if label == "Left":
                                left_hand_coords = hand_coords
                            elif label == "Right":
                                right_hand_coords = hand_coords
                                
                    frame_features = pose_coords + left_hand_coords + right_hand_coords
                    sequence.append(frame_features)
                
                cap.release()
                
                # Delete video file after processing to save disk space
                try:
                    os.remove(video_file)
                except Exception:
                    pass

                if len(sequence) > 5:
                    normalized_seq = interpolate_sequence(sequence, target_len=TARGET_FRAMES)
                    word_dir = os.path.join(DATA_DIR, gloss)
                    os.makedirs(word_dir, exist_ok=True)
                    
                    np.save(os.path.join(word_dir, f"sample_{counts[gloss]}.npy"), normalized_seq)
                    counts[gloss] += 1
                    print(f"[+] Extracted '{gloss}' sample {counts[gloss]} (real-world dataset)")

    except Exception as ex:
        print(f"[-] Processing loop error: {ex}")
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    # For every word, if we didn't reach 20 samples, backfill with synthetic
    print("\n====================================================")
    print("Dataset extraction report:")
    for word in TARGET_TOKENS:
        real_count = counts[word]
        print(f"  Word '{word}': {real_count} real-world samples extracted.")
        if real_count < 20:
            generate_synthetic_samples_for_word(word, real_count, 20 - real_count)
            
    print("[OK] CISLR dataset compilation completed.")

if __name__ == "__main__":
    main()
