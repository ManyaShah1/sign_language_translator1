import os
import cv2
import csv
import urllib.request
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (9, 10), (10, 11), (11, 12),
    (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17)
]

def calculate_orientation(landmarks):
    if not landmarks or len(landmarks) < 21:
        return 0.0, 0.0
        
    # Get coordinates for Wrist (0), Index MCP (5), Pinky MCP (17), Thumb MCP (2)
    # Multiply X by 1.3333 to correct 640x480 aspect ratio distortion
    wrist = np.array([landmarks[0].get('x', 0.0) * 1.3333, landmarks[0].get('y', 0.0), landmarks[0].get('z', 0.0)])
    index_mcp = np.array([landmarks[5].get('x', 0.0) * 1.3333, landmarks[5].get('y', 0.0), landmarks[5].get('z', 0.0)])
    pinky_mcp = np.array([landmarks[17].get('x', 0.0) * 1.3333, landmarks[17].get('y', 0.0), landmarks[17].get('z', 0.0)])
    thumb_mcp = np.array([landmarks[2].get('x', 0.0) * 1.3333, landmarks[2].get('y', 0.0), landmarks[2].get('z', 0.0)])
    
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

def normalize_landmarks(landmarks):
    if not landmarks or len(landmarks) != 21:
        return [0.0] * 63
        
    coords = []
    for lm in landmarks:
        coords.extend([lm.get('x', 0.0) * 1.3333, lm.get('y', 0.0), lm.get('z', 0.0)])
        
    coords = np.array(coords, dtype=np.float32)
    
    wrist = coords[:3].copy()
    for i in range(21):
        coords[i*3 : i*3+3] -= wrist
        
    middle_mcp = coords[9*3 : 9*3+3]
    hand_size = np.linalg.norm(middle_mcp)
    
    if hand_size > 0.001:
        coords /= hand_size
        
    return coords.tolist()

def main():
    print("====================================================")
    print("      SWAYAM HEALTH - LOCAL GESTURE RECORDER        ")
    print("====================================================")
    
    label = input("Enter character sign to record (A-Z, 1-9): ").strip().upper()
    if not label or len(label) != 1:
        print("[-] Error: Label must be a single character.")
        return
        
    dataset_path = 'dataset.csv'
    model_path = 'hand_landmarker.task'
    
    # Download hand landmarker task file if missing
    if not os.path.exists(model_path):
        print("[*] 'hand_landmarker.task' model file not found.")
        print("[*] Downloading model from Google MediaPipe Repository...")
        try:
            url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
            urllib.request.urlretrieve(url, model_path)
            print("[✓] Model downloaded successfully.")
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
        print("[✓] MediaPipe landmarker initialized.")
    except Exception as e:
        print(f"[-] Failed to initialize MediaPipe landmarker: {e}")
        return
        
    print("[*] Opening Webcam...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[-] Error: Could not open webcam.")
        return
        
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    is_recording = False
    saved_frames = 0
    
    print("\n====================================================")
    print("INSTRUCTIONS:")
    print("  - Press SPACEBAR to START / STOP recording frames.")
    print("  - Move your hand slightly to capture multiple angles.")
    print("  - Press ESC or 'q' to quit.")
    print("====================================================\n")
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            print("[-] Error: Failed to capture image.")
            break
            
        # Flip horizontally for mirrored view
        frame = cv2.flip(frame, 1)
        h, w, c = frame.shape
        
        # Run detection using Tasks API
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        results = detector.detect(mp_image)
        
        hand_detected = False
        
        if results.hand_landmarks:
            hand_landmarks = results.hand_landmarks[0]
            hand_detected = True
            
            # Draw circles at hand landmark points
            for lm in hand_landmarks:
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(frame, (cx, cy), 5, (255, 255, 255), -1)
                
            # Draw connections (skeletons)
            for start, end in HAND_CONNECTIONS:
                p1 = hand_landmarks[start]
                p2 = hand_landmarks[end]
                x1, y1 = int(p1.x * w), int(p1.y * h)
                x2, y2 = int(p2.x * w), int(p2.y * h)
                cv2.line(frame, (x1, y1), (x2, y2), (181, 184, 24), 2)  # Teal/cyan-like color (BGR: 181, 184, 24)
                
            # Format and normalize landmarks
            landmarks_list = [{"x": lm.x, "y": lm.y, "z": lm.z} for lm in hand_landmarks]
            is_palm, is_left = calculate_orientation(landmarks_list)
            normalized = normalize_landmarks(landmarks_list)
            
            # Build 130-feature vector
            features = [0.0] * 130
            features[0:63] = normalized
            features[126] = is_palm
            features[127] = is_left
            features[128] = -1.0
            features[129] = -1.0
            
            if is_recording:
                # Write to dataset.csv
                try:
                    with open(dataset_path, 'a', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(features + [label])
                    saved_frames += 1
                except Exception as e:
                    print(f"[-] Error writing to CSV: {e}")
                    
        # Overlay UI status on window
        status_text = f"RECORDING [{label}] - Frames: {saved_frames}" if is_recording else f"PAUSED [{label}]"
        status_color = (0, 0, 255) if is_recording else (255, 0, 0)
        
        cv2.putText(frame, status_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2, cv2.LINE_AA)
        
        if not hand_detected:
            cv2.putText(frame, "No Hand Detected", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2, cv2.LINE_AA)
            
        cv2.imshow("Swayam Health - Dataset Collector", frame)
        
        # Keyboard listener
        key = cv2.waitKey(1) & 0xFF
        if key == 32:  # SPACEBAR
            is_recording = not is_recording
            print(f"[*] Recording: {is_recording}")
        elif key == 27 or key == ord('q'):  # ESC or Q
            break
            
    cap.release()
    cv2.destroyAllWindows()
    print(f"\n[✓] Session closed. Captured {saved_frames} frames under label '{label}'.")
    print(f"[*] Total frames are appended to '{os.path.abspath(dataset_path)}'.")

if __name__ == '__main__':
    main()
