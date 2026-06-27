import os
import cv2
import time
import urllib.request
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Connections for rendering overlay skeletons
POSE_CONNECTIONS = [
    (11, 12), (11, 13), (12, 14), (13, 15), (14, 16)
]
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (9, 10), (10, 11), (11, 12),
    (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17)
]

def main():
    print("====================================================")
    print("      SWAYAM HEALTH - SEQUENCE GESTURE RECORDER     ")
    print("====================================================")
    
    word = input("Enter gesture sign word to record (e.g., THANKYOU): ").strip().upper()
    if not word:
        print("[-] Error: Word label cannot be empty.")
        return
        
    data_dir = "data_sequences"
    word_dir = os.path.join(data_dir, word)
    os.makedirs(word_dir, exist_ok=True)
    
    # Determine next sample index
    existing_samples = [f for f in os.listdir(word_dir) if f.endswith(".npy")]
    next_idx = 0
    if existing_samples:
        indices = []
        for f in existing_samples:
            try:
                # Extract index from 'sample_<idx>.npy'
                idx = int(f.split("_")[1].split(".")[0])
                indices.append(idx)
            except Exception:
                pass
        if indices:
            next_idx = max(indices) + 1
            
    print(f"[OK] Mapped word directory '{word_dir}'. Next sample file: sample_{next_idx}.npy")
    
    hand_model_path = 'hand_landmarker.task'
    pose_model_path = 'pose_landmarker.task'
    
    # Download hand model if missing
    if not os.path.exists(hand_model_path):
        print("[*] Downloading hand landmarker model asset...")
        url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
        urllib.request.urlretrieve(url, hand_model_path)
        
    # Download pose model if missing
    if not os.path.exists(pose_model_path):
        print("[*] Downloading pose landmarker model asset...")
        url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
        urllib.request.urlretrieve(url, pose_model_path)
        
    print("\n[*] Initializing MediaPipe Vision Landmarkers...")
    try:
        hand_options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=hand_model_path),
            num_hands=2,
            running_mode=vision.RunningMode.IMAGE
        )
        pose_options = vision.PoseLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=pose_model_path),
            running_mode=vision.RunningMode.IMAGE
        )
        hand_detector = vision.HandLandmarker.create_from_options(hand_options)
        pose_detector = vision.PoseLandmarker.create_from_options(pose_options)
        print("[OK] Landmarkers initialized successfully.")
    except Exception as e:
        print(f"[-] Failed to initialize landmarkers: {e}")
        return
        
    print("[*] Opening Webcam...")
    # Try camera index 0 first, fallback to 1 if unavailable
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[!] Camera index 0 unavailable, trying index 1...")
        cap = cv2.VideoCapture(1)
        if not cap.isOpened():
            print("[-] Error: Could not open webcam at index 0 or 1.")
            return
        
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    # Warm up camera to allow driver initialization
    print("[*] Warming up webcam...")
    for _ in range(15):
        cap.read()
        time.sleep(0.05)
    
    print("\n====================================================")
    print("INSTRUCTIONS:")
    print("  - Press SPACEBAR to trigger a 3-second countdown.")
    print("  - Perform the sign continuously during recording.")
    print("  - The script will automatically record exactly 45 frames.")
    print("  - Press ESC or 'q' to quit.")
    print("====================================================\n")
    
    recording_state = "IDLE"  # IDLE, COUNTDOWN, RECORDING
    countdown_start = 0.0
    recorded_frames = []
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            # Skip frame and retry instead of crashing on driver delays
            time.sleep(0.01)
            continue
            
        frame = cv2.flip(frame, 1)  # Mirror for matching client
        h, w, c = frame.shape
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        
        pose_results = pose_detector.detect(mp_image)
        hand_results = hand_detector.detect(mp_image)
        
        pose_coords = [0.0] * 12
        left_hand_coords = [0.0] * 63
        right_hand_coords = [0.0] * 63
        
        anchor_x, anchor_y, anchor_z = 0.5, 0.5, 0.0
        
        # 1. Process Pose features
        if pose_results.pose_landmarks and len(pose_results.pose_landmarks) > 0:
            landmarks = pose_results.pose_landmarks[0]
            left_shoulder = landmarks[11]
            right_shoulder = landmarks[12]
            left_elbow = landmarks[13]
            right_elbow = landmarks[14]
            
            # Torso midpoint global origin
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
            
            # Draw Pose skeleton connections
            for p1_idx, p2_idx in POSE_CONNECTIONS:
                p1 = landmarks[p1_idx]
                p2 = landmarks[p2_idx]
                cv2.line(frame, (int(p1.x * w), int(p1.y * h)), (int(p2.x * w), int(p2.y * h)), (0, 255, 0), 2)
                
        # 2. Process Hand features
        if hand_results.hand_landmarks:
            for hand_idx, hand_lms in enumerate(hand_results.hand_landmarks):
                label = hand_results.handedness[hand_idx][0].category_name
                
                hand_coords = []
                for lm in hand_lms:
                    hand_coords.extend([(1.0 - lm.x) - anchor_x, lm.y - anchor_y, lm.z - anchor_z])
                    
                if label == "Left":
                    left_hand_coords = hand_coords
                elif label == "Right":
                    right_hand_coords = hand_coords
                    
                # Draw hand connections
                for start, end in HAND_CONNECTIONS:
                    p1 = hand_lms[start]
                    p2 = hand_lms[end]
                    cv2.line(frame, (int(p1.x * w), int(p1.y * h)), (int(p2.x * w), int(p2.y * h)), (181, 184, 24), 2)
                    
        frame_features = pose_coords + left_hand_coords + right_hand_coords
        
        # UI overlays based on state
        if recording_state == "IDLE":
            cv2.putText(frame, f"READY: '{word}' | Next Sample: {next_idx}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 127, 0), 2)
            cv2.putText(frame, "Press SPACE to start countdown", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
            
        elif recording_state == "COUNTDOWN":
            elapsed = time.time() - countdown_start
            remaining = 3.0 - elapsed
            if remaining <= 0:
                recording_state = "RECORDING"
                recorded_frames = []
                print("[*] Recording started!")
            else:
                cv2.putText(frame, f"GET READY: {int(remaining) + 1}...", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 165, 255), 3)
                
        elif recording_state == "RECORDING":
            recorded_frames.append(frame_features)
            progress = len(recorded_frames)
            
            # Draw red record dot and progress bar
            cv2.circle(frame, (30, 35), 8, (0, 0, 255), -1)
            cv2.putText(frame, f"RECORDING '{word}': {progress}/45 frames", (50, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            if progress >= 45:
                # Save NumPy array
                seq_arr = np.array(recorded_frames, dtype=np.float32)
                save_path = os.path.join(word_dir, f"sample_{next_idx}.npy")
                np.save(save_path, seq_arr)
                print(f"[✓] Saved sample file successfully to: {save_path}")
                
                # Update next sample ID
                next_idx += 1
                recording_state = "IDLE"
                recorded_frames = []
                
        cv2.imshow("Swayam Health - Sequence Recorder", frame)
        
        # Keyboard commands
        key = cv2.waitKey(1) & 0xFF
        if key == 32:  # SPACEBAR
            if recording_state == "IDLE":
                recording_state = "COUNTDOWN"
                countdown_start = time.time()
        elif key == 27 or key == ord('q'):  # ESC or Q
            break
            
    cap.release()
    cv2.destroyAllWindows()
    print("[OK] Sequence recorder closed.")

if __name__ == '__main__':
    main()
