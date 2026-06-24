import asyncio
import json
import math
import random
import os
import sys
import subprocess

# Auto-resolve deep learning environment dependencies before starting service loop
MODEL_NAME = 'isl_model_advanced.tflite'
has_model = os.path.exists(MODEL_NAME) or os.path.exists(os.path.join('python_server', MODEL_NAME))

required_packages = ["numpy", "websockets"]

if has_model:
    # Try importing ai_edge_litert, tflite_runtime or tensorflow.
    litert_installed = False
    try:
        import ai_edge_litert.interpreter
        litert_installed = True
    except ImportError:
        try:
            import tflite_runtime.interpreter
            litert_installed = True
        except ImportError:
            try:
                import tensorflow
                litert_installed = True
            except ImportError:
                pass
            
    if not litert_installed:
        # On Python 3.14+ on Windows, ai-edge-litert is the only standalone installer.
        if sys.version_info >= (3, 14):
            required_packages.append("ai-edge-litert")
        else:
            required_packages.append("tflite-runtime")

for package in required_packages:
    import_name = package.replace("-", "_")
    try:
        __import__(import_name)
    except ImportError:
        print(f"[!] Dependency '{package}' missing. Auto-installing via pip...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

import numpy as np
import websockets

# Load TFLite / LiteRT interpreter
tflite_interpreter = None
try:
    import ai_edge_litert.interpreter as litert
    tflite_interpreter = litert.Interpreter
    print("[✓] Successfully loaded ai_edge_litert (LiteRT) interpreter.")
except ImportError:
    try:
        import tflite_runtime.interpreter as tflite
        tflite_interpreter = tflite.Interpreter
        print("[✓] Successfully loaded tflite_runtime interpreter.")
    except ImportError:
        try:
            import tensorflow as tf
            tflite_interpreter = tf.lite.Interpreter
            print("[✓] Successfully loaded tensorflow.lite interpreter.")
        except ImportError:
            print("[!] Warning: Neither ai_edge_litert, tflite_runtime, nor tensorflow are available.")


# Port and Host configuration
HOST = "0.0.0.0"
PORT = 8768

class RealTimeASLTranslationEngine:
    """
    A real-time Indian Sign Language translation engine.
    It takes raw keypoint frame streams from the Flutter client,
    calculates hand orientation/handedness, normalizes 3D landmarks relative to the wrist/size,
    runs classification using the KairoAI TFLite model, and aggregates letters into spelled text.
    """
    def __init__(self):
        self.model_path = 'isl_model_advanced.tflite'
        self.interpreter = None
        self.input_details = None
        self.output_details = None
        
        # Spelling buffer state
        self.spelled_text = ""
        self.current_stable_char = None
        self.stable_frame_count = 0
        self.no_hand_frame_count = 0
        self.last_appended_char = None
        self.frame_counter = 0
        self.last_wrist_pos = None
        self.velocity_threshold = 0.05  # Normalized distance per frame threshold
        
        self.labels = [
            'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
            'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T',
            'U', 'V', 'W', 'X', 'Y', 'Z', '1', '2', '3', '4',
            '5', '6', '7', '8', '9'
        ]
        
        # Dictionary of common medical and health words for spelling autocorrect
        self.dictionary = [
            "HELLO", "HELP", "DOCTOR", "FEVER", "PAIN", "SICK", "HEADACHE", 
            "MEDICINE", "SAD", "HAPPY", "THANK", "YOU", "PLEASE", "YES", "NO", 
            "COLD", "HURT", "ACCIDENT", "EMERGENCY"
        ]
        
        self.pickle_path = 'isl_model_advanced.pkl'
        self.dataset_path = 'dataset.csv'
        self.use_pickle = False
        self.clf = None
        self.load_dataset_counts()
        self.load_model()

    def edit_distance(self, s1, s2):
        """Standard Levenshtein distance algorithm (zero external dependencies)."""
        if len(s1) < len(s2):
            return self.edit_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    def autocorrect_word(self, word):
        """Returns the closest word in the dictionary if within distance threshold."""
        word = word.upper().strip()
        if not word or word in self.dictionary:
            return word
            
        best_word = word
        min_dist = 9999
        
        for dict_word in self.dictionary:
            dist = self.edit_distance(word, dict_word)
            # Allow correction if distance is small (max edits = half word length)
            if dist < min_dist and dist <= max(1, len(word) // 2):
                min_dist = dist
                best_word = dict_word
                
        return best_word

    def load_model(self):
        """Loads custom scikit-learn pickle model if it exists, otherwise falls back to TFLite."""
        self.pickle_path = 'isl_model_advanced.pkl'
        resolved_pkl = self.pickle_path
        if not os.path.exists(resolved_pkl) and os.path.exists(os.path.join('python_server', resolved_pkl)):
            resolved_pkl = os.path.join('python_server', resolved_pkl)

        if os.path.exists(resolved_pkl):
            try:
                import pickle
                with open(resolved_pkl, 'rb') as f:
                    self.clf = pickle.load(f)
                self.use_pickle = True
                print(f"[✓] Successfully loaded custom scikit-learn model: '{resolved_pkl}'")
                return
            except Exception as e:
                print(f"[-] Error loading custom pickle model: {e}")

        self.use_pickle = False
        self.clf = None
        self.load_tflite_model()

    def load_dataset_counts(self):
        """Scan dataset.csv to calculate counts per label."""
        self.label_counts = {l: 0 for l in self.labels}
        self.dataset_path = 'dataset.csv'
        resolved_csv = self.dataset_path
        if not os.path.exists(resolved_csv) and os.path.exists(os.path.join('python_server', resolved_csv)):
            resolved_csv = os.path.join('python_server', resolved_csv)

        if os.path.exists(resolved_csv):
            try:
                with open(resolved_csv, 'r') as f:
                    for line in f:
                        parts = line.strip().split(',')
                        if parts:
                            label = parts[-1]
                            if label in self.label_counts:
                                self.label_counts[label] += 1
                print(f"[✓] Loaded dataset counts from '{resolved_csv}'. Total samples: {sum(self.label_counts.values())}")
            except Exception as e:
                print(f"[-] Error reading dataset counts: {e}")

    def save_record_frame(self, landmarks, label):
        """Normalize coordinates, append to dataset.csv, and update in-memory count."""
        is_palm, is_left = self.calculate_orientation(landmarks)
        normalized = self.normalize_landmarks(landmarks)

        features = [0.0] * 130
        features[0:63] = normalized
        features[126] = is_palm
        features[127] = is_left
        features[128] = -1.0
        features[129] = -1.0

        resolved_csv = self.dataset_path
        if not os.path.exists(resolved_csv) and os.path.exists(os.path.join('python_server', resolved_csv)):
            resolved_csv = os.path.join('python_server', resolved_csv)

        try:
            with open(resolved_csv, 'a') as f:
                feature_str = ",".join(f"{val:.6f}" for val in features)
                f.write(f"{feature_str},{label}\n")

            if label not in self.label_counts:
                self.label_counts[label] = 0
            self.label_counts[label] += 1

            return self.label_counts[label]
        except Exception as e:
            print(f"[-] Failed to save record frame: {e}")
            return self.label_counts.get(label, 0)

    def train_custom_model(self):
        """Train a scikit-learn MLP classifier on dataset.csv."""
        resolved_csv = self.dataset_path
        if not os.path.exists(resolved_csv) and os.path.exists(os.path.join('python_server', resolved_csv)):
            resolved_csv = os.path.join('python_server', resolved_csv)

        if not os.path.exists(resolved_csv):
            raise FileNotFoundError("Dataset file 'dataset.csv' does not exist. Record some frames first.")

        X = []
        y = []
        with open(resolved_csv, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) == 131:
                    X.append([float(val) for val in parts[:-1]])
                    y.append(parts[-1])

        if len(X) < 10:
            raise ValueError(f"Insufficient training data. Only {len(X)} samples found. Please record more signs.")

        import numpy as np
        X = np.array(X, dtype=np.float32)
        y = np.array(y)

        from sklearn.model_selection import train_test_split
        from sklearn.neural_network import MLPClassifier
        import pickle

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        clf = MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=300, random_state=42)
        clf.fit(X_train, y_train)

        accuracy = float(clf.score(X_test, y_test))

        clf.fit(X, y)

        resolved_pkl = self.pickle_path
        if not os.path.exists(resolved_pkl) and os.path.exists(os.path.join('python_server', resolved_pkl)):
            resolved_pkl = os.path.join('python_server', resolved_pkl)

        with open(resolved_pkl, 'wb') as f:
            pickle.dump(clf, f)

        self.clf = clf
        self.use_pickle = True

        return accuracy, len(X)

    def load_tflite_model(self):
        resolved_path = None
        if os.path.exists(self.model_path):
            resolved_path = self.model_path
        elif os.path.exists(os.path.join('python_server', self.model_path)):
            resolved_path = os.path.join('python_server', self.model_path)
            
        if resolved_path and tflite_interpreter is not None:
            try:
                self.interpreter = tflite_interpreter(model_path=resolved_path)
                self.interpreter.allocate_tensors()
                self.input_details = self.interpreter.get_input_details()
                self.output_details = self.interpreter.get_output_details()
                print(f"[✓] Successfully loaded ISL TFLite model: '{resolved_path}'")
            except Exception as e:
                print(f"[-] Error loading TFLite model: {e}")
        else:
            print(f"[!] Warning: TFLite model not found or interpreter unavailable.")

    def calculate_orientation(self, landmarks):
        """
        Calculate whether palm or back of hand is facing the camera.
        Returns: is_palm_facing (1.0 or 0.0), is_left_hand (1.0 or 0.0)
        """
        if not landmarks or len(landmarks) < 21:
            return 0.0, 0.0
            
        # Get coordinates for Wrist (0), Index MCP (5), Pinky MCP (17), Thumb MCP (2)
        # Multiply X by 1.3333 to correct 640x480 aspect ratio distortion
        wrist = np.array([landmarks[0].get('x', 0.0) * 1.3333, landmarks[0].get('y', 0.0), landmarks[0].get('z', 0.0)])
        index_mcp = np.array([landmarks[5].get('x', 0.0) * 1.3333, landmarks[5].get('y', 0.0), landmarks[5].get('z', 0.0)])
        pinky_mcp = np.array([landmarks[17].get('x', 0.0) * 1.3333, landmarks[17].get('y', 0.0), landmarks[17].get('z', 0.0)])
        thumb_mcp = np.array([landmarks[2].get('x', 0.0) * 1.3333, landmarks[2].get('y', 0.0), landmarks[2].get('z', 0.0)])
        
        # Vectors on the palm plane
        v1 = index_mcp - wrist
        v2 = pinky_mcp - wrist
        
        # Normal vector to palm plane
        normal = np.cross(v1, v2)
        z_component = normal[2]
        
        # Heuristically estimate handedness (Left vs Right)
        thumb_is_left = thumb_mcp[0] < pinky_mcp[0]
        is_palm = 1.0 if z_component > 0 else 0.0
        is_left = 1.0 if thumb_is_left == (is_palm == 0.0) else 0.0
        
        if is_left:
            z_component = -z_component
            
        is_palm_facing = 1.0 if z_component > 0 else 0.0
        return is_palm_facing, is_left

    def normalize_landmarks(self, landmarks):
        """Normalize coordinates relative to wrist and scale to hand size."""
        if not landmarks or len(landmarks) != 21:
            return [0.0] * 63
            
        coords = []
        for lm in landmarks:
            # Scale X by 1.3333 to correct aspect ratio distortion
            coords.extend([lm.get('x', 0.0) * 1.3333, lm.get('y', 0.0), lm.get('z', 0.0)])
            
        coords = np.array(coords, dtype=np.float32)
        
        # Shift relative to wrist (first landmark)
        wrist = coords[:3].copy()
        for i in range(21):
            coords[i*3 : i*3+3] -= wrist
            
        # Scale by hand size (wrist to middle finger MCP landmark 9)
        middle_mcp = coords[9*3 : 9*3+3]
        hand_size = np.linalg.norm(middle_mcp)
        
        if hand_size > 0.001:
            coords /= hand_size
            
        return coords.tolist()

    def is_hand_moving(self, landmarks):
        if not landmarks or len(landmarks) < 21:
            return False, 0.0
            
        # Track the wrist landmark (index 0) with aspect ratio correction
        current_wrist = np.array([landmarks[0].get('x', 0.0) * 1.3333, landmarks[0].get('y', 0.0)])
        
        if self.last_wrist_pos is None:
            self.last_wrist_pos = current_wrist
            return False, 0.0
            
        # Compute Euclidean distance
        distance = float(np.linalg.norm(current_wrist - self.last_wrist_pos))
        self.last_wrist_pos = current_wrist
        
        # If distance exceeds threshold, hand is moving too fast for stable prediction
        return distance > self.velocity_threshold, distance

    def process_frame(self, landmarks):
        """Processes a frame containing 21 coordinate points and returns prediction."""
        # Capture raw landmarks to raw_landmarks.json for diagnostics
        if landmarks and len(landmarks) == 21:
            if not hasattr(self, 'captured_frames'):
                self.captured_frames = []
            if len(self.captured_frames) < 100:
                self.captured_frames.append(landmarks)
                if len(self.captured_frames) == 100:
                    try:
                        with open('raw_landmarks.json', 'w') as f:
                            json.dump(self.captured_frames, f)
                        print("[✓] Diagnostic log: Saved 100 raw landmark frames to raw_landmarks.json")
                    except Exception as ex:
                        print(f"[-] Failed to save diagnostic raw landmarks: {ex}")

        # Handle empty/missing hand frames (detect hand removal to spell spaces)
        if not landmarks or len(landmarks) != 21:
            self.no_hand_frame_count += 1
            if self.no_hand_frame_count == 30:  # ~1 second at 30 FPS
                if self.spelled_text and not self.spelled_text.endswith(" "):
                    # Extract the last word to run spelling autocorrect
                    words = self.spelled_text.split(" ")
                    last_word = words[-1]
                    corrected = self.autocorrect_word(last_word)
                    
                    if corrected != last_word:
                        print(f"[*] Autocorrected spelling: '{last_word}' -> '{corrected}'")
                        words[-1] = corrected
                        self.spelled_text = " ".join(words)
                        
                    self.spelled_text += " "
                    self.last_appended_char = None
            self.last_wrist_pos = None  # Reset wrist tracking
            return {
                "translation": self.spelled_text if self.spelled_text else "Waiting for hand...",
                "confidence": 1.0,
                "velocity": 0.0,
                "status": "Idle"
            }
            
        self.no_hand_frame_count = 0
        self.frame_counter += 1

        # Velocity checking
        is_moving, velocity = self.is_hand_moving(landmarks)
        if is_moving:
            return {
                "translation": self.spelled_text if self.spelled_text else "Moving hand...",
                "confidence": 0.0,
                "velocity": round(velocity, 4),
                "status": "Moving..."
            }
        
        # Calculate features
        is_palm, is_left = self.calculate_orientation(landmarks)
        normalized = self.normalize_landmarks(landmarks)
        
        # Build 130-feature vector expected by KairoAI model
        features = [0.0] * 130
        
        # Hand 1 features (0 to 62)
        features[0:63] = normalized
        # Hand 1 orientation (126, 127)
        features[126] = is_palm
        features[127] = is_left
        
        # Hand 2 features are filled with defaults (landmarks = 0, orientation = -1.0)
        features[128] = -1.0
        features[129] = -1.0
        
        # Run inference if model is loaded
        if self.use_pickle and self.clf is not None:
            try:
                input_data = np.array(features, dtype=np.float32).reshape(1, -1)
                prediction_probs = self.clf.predict_proba(input_data)[0]
                
                best_class_idx = np.argmax(prediction_probs)
                confidence = float(prediction_probs[best_class_idx])
                predicted_char = self.clf.classes_[best_class_idx]
            except Exception as e:
                print(f"[-] Pickle inference failed: {e}")
                self.use_pickle = False
                return self.process_frame(landmarks)
        elif self.interpreter is not None:
            input_data = np.array(features, dtype=np.float32).reshape(1, -1)
            self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
            self.interpreter.invoke()
            prediction_probs = self.interpreter.get_tensor(self.output_details[0]['index'])[0]
            
            best_class_idx = np.argmax(prediction_probs)
            confidence = float(prediction_probs[best_class_idx])
            predicted_char = self.labels[best_class_idx]
        else:
            return {
                "translation": "No model loaded",
                "confidence": 0.0,
                "velocity": 0.0,
                "status": "Offline"
            }

        if self.frame_counter % 30 == 0:
            print(f"[DEBUG Engine] frame={self.frame_counter} | is_palm={is_palm} | is_left={is_left} | predicted={predicted_char} ({confidence:.2f})")
        
        # Stable filtering (consecutive matching character frames)
        if confidence >= 0.60:
            if predicted_char == self.current_stable_char:
                self.stable_frame_count += 1
            else:
                self.current_stable_char = predicted_char
                self.stable_frame_count = 1
                
            # Spell letter after 8 stable frames (~0.27 seconds)
            if self.stable_frame_count == 8:
                if self.spelled_text == "" or self.last_appended_char != predicted_char:
                    # Append the character to text stream
                    if self.spelled_text.endswith(" "):
                        self.spelled_text += predicted_char
                    else:
                        self.spelled_text += predicted_char
                    self.last_appended_char = predicted_char
        else:
            self.current_stable_char = None
            self.stable_frame_count = 0
            
        return {
            "translation": self.spelled_text if self.spelled_text else predicted_char,
            "confidence": round(confidence, 2),
            "velocity": 0.0,
            "status": f"Detected: {predicted_char}" if confidence >= 0.60 else "Analyzing..."
        }


# Instantiate global engine to preserve model memory across connects
global_engine = RealTimeASLTranslationEngine()

async def handle_connection(websocket, path=None):
    client_ip = websocket.remote_address[0]
    print(f"\n[+] Active diagnostic link established from client: {client_ip}")
    
    # Reset spelling states on new connections
    global_engine.spelled_text = ""
    global_engine.last_appended_char = None
    global_engine.current_stable_char = None
    global_engine.stable_frame_count = 0
    global_engine.no_hand_frame_count = 0
    global_engine.last_wrist_pos = None
    
    frame_count = 0

    try:
        async for message in websocket:
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                print(f"[-] Received unparseable message block from {client_ip}")
                continue

            msg_type = payload.get("type", "coordinates")

            if msg_type == "ping":
                await websocket.send(json.dumps({"type": "pong"}))

            elif msg_type == "clear_buffer" or msg_type == "clear":
                global_engine.spelled_text = ""
                global_engine.last_appended_char = None
                global_engine.current_stable_char = None
                global_engine.stable_frame_count = 0
                print("[*] Engine spelling buffer cleared.")
                
                await websocket.send(json.dumps({
                    "type": "translation_result",
                    "translation": "",
                    "confidence": 1.0,
                    "status": "Idle",
                    "velocity": 0.0,
                    "timestamp": payload.get("timestamp", 0)
                }))

            elif msg_type == "backspace":
                if global_engine.spelled_text:
                    global_engine.spelled_text = global_engine.spelled_text[:-1]
                global_engine.last_appended_char = None
                global_engine.current_stable_char = None
                global_engine.stable_frame_count = 0
                print("[*] Engine spelling buffer backspaced.")
                
                await websocket.send(json.dumps({
                    "type": "translation_result",
                    "translation": global_engine.spelled_text,
                    "confidence": 1.0,
                    "status": "Idle",
                    "velocity": 0.0,
                    "timestamp": payload.get("timestamp", 0)
                }))

            elif msg_type == "space":
                if global_engine.spelled_text and not global_engine.spelled_text.endswith(" "):
                    global_engine.spelled_text += " "
                global_engine.last_appended_char = None
                global_engine.current_stable_char = None
                global_engine.stable_frame_count = 0
                print("[*] Engine spelling buffer space appended.")
                
                await websocket.send(json.dumps({
                    "type": "translation_result",
                    "translation": global_engine.spelled_text,
                    "confidence": 1.0,
                    "status": "Idle",
                    "velocity": 0.0,
                    "timestamp": payload.get("timestamp", 0)
                }))

            elif msg_type == "get_dataset_info":
                await websocket.send(json.dumps({
                    "type": "dataset_info",
                    "counts": global_engine.label_counts
                }))

            elif msg_type == "record_frame":
                landmarks = payload.get("landmarks", [])
                label = payload.get("label", "")
                if landmarks and len(landmarks) == 21 and label:
                    count = global_engine.save_record_frame(landmarks, label)
                    await websocket.send(json.dumps({
                        "type": "record_status",
                        "label": label,
                        "count": count
                    }))

            elif msg_type == "train_model":
                print("[*] Received train_model request. Retraining custom classifier...")
                try:
                    accuracy, total_samples = await asyncio.to_thread(global_engine.train_custom_model)
                    await websocket.send(json.dumps({
                        "type": "training_completed",
                        "status": "success",
                        "accuracy": accuracy,
                        "total_samples": total_samples
                    }))
                    print(f"[✓] Custom classifier trained successfully. Accuracy: {accuracy:.4f} on {total_samples} samples.")
                except Exception as ex:
                    print(f"[-] Training failed: {ex}")
                    await websocket.send(json.dumps({
                        "type": "training_completed",
                        "status": "error",
                        "message": str(ex)
                    }))

            elif msg_type == "delete_custom_model":
                print("[*] Received request to delete custom model.")
                resolved_pkl = global_engine.pickle_path
                if not os.path.exists(resolved_pkl) and os.path.exists(os.path.join('python_server', resolved_pkl)):
                    resolved_pkl = os.path.join('python_server', resolved_pkl)
                try:
                    if os.path.exists(resolved_pkl):
                        os.remove(resolved_pkl)
                    global_engine.use_pickle = False
                    global_engine.clf = None
                    global_engine.load_tflite_model()
                    await websocket.send(json.dumps({
                        "type": "delete_custom_model_completed",
                        "status": "success"
                    }))
                    print("[✓] Custom model deleted and fallback to TFLite completed.")
                except Exception as ex:
                    print(f"[-] Error deleting custom model: {ex}")
                    await websocket.send(json.dumps({
                        "type": "delete_custom_model_completed",
                        "status": "error",
                        "message": str(ex)
                    }))

            elif msg_type == "coordinates":
                frame_count += 1
                landmarks = payload.get("landmarks", [])
                
                # Process landmarks via neural translation engine
                result = global_engine.process_frame(landmarks)
                
                # Periodically display telemetry statistics in the host console
                if frame_count % 30 == 0:
                    print(f"[*] Frames parsed: {frame_count} | Spelled Text: '{global_engine.spelled_text}' | Status: {result['status']}")

                if result:
                    await websocket.send(json.dumps({
                        "type": "translation_result",
                        "translation": result["translation"],
                        "confidence": result["confidence"],
                        "status": result["status"],
                        "velocity": result["velocity"],
                        "timestamp": payload.get("timestamp", 0)
                    }))

    except Exception as e:
        print(f"[-] Session disruption logged for client {client_ip}: {e}")
    finally:
        print(f"[-] Client connection closed safely: {client_ip}")


async def main():
    print("====================================================")
    print("      SWAYAM HEALTH LOCAL INFERENCE SERVER          ")
    print("         Indian Sign Language KairoAI TFLite        ")
    print("====================================================")
    print(f"Running WebSocket Server on: ws://{HOST}:{PORT}")
    print("Press Ctrl+C to safely stop the inference host daemon.")
    print("----------------------------------------------------")

    async with websockets.serve(handle_connection, HOST, PORT):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[-] Inference server stopped via manual user break command.")