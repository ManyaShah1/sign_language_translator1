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
        
        self.labels = [
            'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
            'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T',
            'U', 'V', 'W', 'X', 'Y', 'Z', '1', '2', '3', '4',
            '5', '6', '7', '8', '9'
        ]
        
        self.load_tflite_model()

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
        wrist = np.array([landmarks[0].get('x', 0.0), landmarks[0].get('y', 0.0), landmarks[0].get('z', 0.0)])
        index_mcp = np.array([landmarks[5].get('x', 0.0), landmarks[5].get('y', 0.0), landmarks[5].get('z', 0.0)])
        pinky_mcp = np.array([landmarks[17].get('x', 0.0), landmarks[17].get('y', 0.0), landmarks[17].get('z', 0.0)])
        thumb_mcp = np.array([landmarks[2].get('x', 0.0), landmarks[2].get('y', 0.0), landmarks[2].get('z', 0.0)])
        
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
            coords.extend([lm.get('x', 0.0), lm.get('y', 0.0), lm.get('z', 0.0)])
            
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

    def process_frame(self, landmarks):
        """Processes a frame containing 21 coordinate points and returns prediction."""
        # Handle empty/missing hand frames (detect hand removal to spell spaces)
        if not landmarks or len(landmarks) != 21:
            self.no_hand_frame_count += 1
            if self.no_hand_frame_count == 30:  # ~1 second at 30 FPS
                if self.spelled_text and not self.spelled_text.endswith(" "):
                    self.spelled_text += " "
                    self.last_appended_char = None
            return {
                "translation": self.spelled_text if self.spelled_text else "Waiting for hand...",
                "confidence": 1.0,
                "velocity": 0.0,
                "status": "Idle"
            }
            
        self.no_hand_frame_count = 0
        
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
        if self.interpreter is not None:
            input_data = np.array(features, dtype=np.float32).reshape(1, -1)
            self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
            self.interpreter.invoke()
            prediction_probs = self.interpreter.get_tensor(self.output_details[0]['index'])[0]
            
            best_class_idx = np.argmax(prediction_probs)
            confidence = float(prediction_probs[best_class_idx])
            predicted_char = self.labels[best_class_idx]
            
            # Stable filtering (consecutive matching character frames)
            if confidence >= 0.60:
                if predicted_char == self.current_stable_char:
                    self.stable_frame_count += 1
                else:
                    self.current_stable_char = predicted_char
                    self.stable_frame_count = 1
                    
                # Spell letter after 5 stable frames (~0.17 seconds)
                if self.stable_frame_count == 5:
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
        else:
            return {
                "translation": "TFLite model not loaded",
                "confidence": 0.0,
                "velocity": 0.0,
                "status": "Offline"
            }


async def handle_connection(websocket, path=None):
    client_ip = websocket.remote_address[0]
    print(f"\n[+] Active diagnostic link established from client: {client_ip}")
    
    engine = RealTimeASLTranslationEngine()
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
                engine.spelled_text = ""
                engine.last_appended_char = None
                engine.current_stable_char = None
                engine.stable_frame_count = 0
                print("[*] Engine spelling buffer cleared.")
                
                await websocket.send(json.dumps({
                    "type": "translation_result",
                    "translation": "",
                    "confidence": 1.0,
                    "status": "Idle",
                    "velocity": 0.0,
                    "timestamp": payload.get("timestamp", 0)
                }))

            elif msg_type == "coordinates":
                frame_count += 1
                landmarks = payload.get("landmarks", [])
                
                # Process landmarks via neural translation engine
                result = engine.process_frame(landmarks)
                
                # Periodically display telemetry statistics in the host console
                if frame_count % 30 == 0:
                    print(f"[*] Frames parsed: {frame_count} | Spelled Text: '{engine.spelled_text}' | Status: {result['status']}")

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