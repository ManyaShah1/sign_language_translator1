import asyncio
import json
import math
import random

# Port and Host configuration
HOST = "0.0.0.0"
PORT = 8768

# Preset Continuous ASL Sentences for simulation mapping
ASL_SENTENCES = [
    "Hello, welcome to Swayam Health.",
    "I need medical assistance.",
    "Where is the doctor's room?",
    "Please check my vitals and blood pressure.",
    "Thank you for your help.",
    "I am feeling dizzy and weak.",
    "Can you print my health report?",
    "Everything is good, thank you."
]

class ContinuousASLModelSimulator:
    """
    A simulator of a Connectionist Temporal Classification (CTC) sequence decoder.
    It processes streams of hand coordinates, calculates motion velocity/variance,
    and decodes the patterns into continuous English sentences.
    """
    def __init__(self):
        self.frame_buffer = []
        self.max_buffer_size = 60  # ~2 seconds of frames at 30fps
        self.sentence_index = 0
        self.last_predicted_sentence = ""
        self.stationary_count = 0
        
    def process_frame(self, landmarks):
        """
        Processes a single frame of landmarks.
        landmarks: List of dicts/lists containing [x, y, z] for each joint.
        """
        if not landmarks or len(landmarks) == 0:
            return None
            
        # Add to frame buffer
        self.frame_buffer.append(landmarks)
        if len(self.frame_buffer) > self.max_buffer_size:
            self.frame_buffer.pop(0)
            
        # Calculate stats (e.g. centroid movement, hand size)
        centroid = self._calculate_centroid(landmarks)
        
        # We simulate gesture classification based on movement patterns.
        # If we have at least 15 frames, we can analyze the trajectory.
        if len(self.frame_buffer) >= 20:
            velocity = self._calculate_average_velocity()
            spatial_spread = self._calculate_spatial_spread(landmarks)
            
            # If the hand is moving significantly
            if velocity > 0.015:
                self.stationary_count = 0
                # Simulate running a CTC Network prediction
                # Let's cyclicly select sentences to simulate dynamic translation of sentences
                predicted = ASL_SENTENCES[self.sentence_index % len(ASL_SENTENCES)]
                if predicted != self.last_predicted_sentence:
                    self.last_predicted_sentence = predicted
                    self.sentence_index += 1
                    return {
                        "translation": predicted,
                        "confidence": round(random.uniform(0.85, 0.99), 2),
                        "velocity": round(velocity, 4),
                        "landmarks_count": len(landmarks),
                        "status": "Translating..."
                    }
            else:
                self.stationary_count += 1
                # If hand is stationary for more than 40 frames (~1.5s), translation is stable
                if self.stationary_count > 40 and self.last_predicted_sentence:
                    result = {
                        "translation": self.last_predicted_sentence,
                        "confidence": 1.0,
                        "velocity": round(velocity, 4),
                        "landmarks_count": len(landmarks),
                        "status": "Finalized Sentence"
                    }
                    return result
                    
        return None

    def _calculate_centroid(self, landmarks):
        xs, ys, zs = [], [], []
        # Support list of lists [x, y, z] or list of dicts {"x": x, "y": y, "z": z}
        for pt in landmarks:
            if isinstance(pt, dict):
                xs.append(pt.get("x", 0.0))
                ys.append(pt.get("y", 0.0))
                zs.append(pt.get("z", 0.0))
            elif isinstance(pt, (list, tuple)) and len(pt) >= 3:
                xs.append(pt[0])
                ys.append(pt[1])
                zs.append(pt[2])
        if not xs:
            return (0, 0, 0)
        return (sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs))

    def _calculate_average_velocity(self):
        """Calculates distance moved by hand centroid in recent frames"""
        if len(self.frame_buffer) < 2:
            return 0.0
        
        total_dist = 0.0
        prev_centroid = self._calculate_centroid(self.frame_buffer[0])
        for frame in self.frame_buffer[1:]:
            curr_centroid = self._calculate_centroid(frame)
            dist = math.sqrt(
                (curr_centroid[0] - prev_centroid[0])**2 +
                (curr_centroid[1] - prev_centroid[1])**2 +
                (curr_centroid[2] - prev_centroid[2])**2
            )
            total_dist += dist
            prev_centroid = curr_centroid
            
        return total_dist / (len(self.frame_buffer) - 1)

    def _calculate_spatial_spread(self, landmarks):
        """Calculates bounding box size of the hand landmarks"""
        xs = [pt.get("x", 0.0) if isinstance(pt, dict) else pt[0] for pt in landmarks]
        ys = [pt.get("y", 0.0) if isinstance(pt, dict) else pt[1] for pt in landmarks]
        if not xs:
            return 0.0
        return (max(xs) - min(xs)) * (max(ys) - min(ys))


async def handle_connection(websocket, path=None):
    client_ip = websocket.remote_address[0]
    print(f"\n[+] Client connected from: {client_ip}")
    
    # Initialize translator simulator
    model = ContinuousASLModelSimulator()
    frame_count = 0
    
    try:
        async for message in websocket:
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                print(f"[-] Received invalid JSON from {client_ip}")
                continue
                
            msg_type = payload.get("type", "coordinates")
            
            if msg_type == "ping":
                # Heartbeat
                await websocket.send(json.dumps({"type": "pong"}))
                
            elif msg_type == "coordinates":
                frame_count += 1
                landmarks = payload.get("landmarks", [])
                
                # Run simulated inference
                result = model.process_frame(landmarks)
                
                # Periodically print input stream info in console
                if frame_count % 30 == 0:
                    avg_v = model._calculate_average_velocity()
                    print(f"[*] Received {frame_count} frames. Active buffer size: {len(model.frame_buffer)}. Avg Velocity: {avg_v:.4f}")
                
                # If model successfully translated a continuous segment
                if result:
                    print(f"\n[!] INFERENCE SUCCESS:")
                    print(f"    - Sentence: '{result['translation']}'")
                    print(f"    - Confidence: {result['confidence']*100}%")
                    print(f"    - Status: {result['status']}")
                    
                    # Send response back to Flutter
                    await websocket.send(json.dumps({
                        "type": "translation_result",
                        "translation": result["translation"],
                        "confidence": result["confidence"],
                        "status": result["status"],
                        "velocity": result["velocity"],
                        "timestamp": payload.get("timestamp", 0)
                    }))
                    
            elif msg_type == "gesture_select":
                # Let user trigger a direct gesture simulation from the UI
                gesture = payload.get("gesture", "Wave Hand")
                idx = payload.get("index", 0)
                selected_phrase = ASL_SENTENCES[idx % len(ASL_SENTENCES)]
                print(f"\n[Direct Trigger] Gesture: '{gesture}' -> Translated to: '{selected_phrase}'")
                
                await websocket.send(json.dumps({
                    "type": "translation_result",
                    "translation": selected_phrase,
                    "confidence": 0.98,
                    "status": "Direct Inference Completed",
                    "velocity": 0.08,
                    "timestamp": payload.get("timestamp", 0)
                }))
                
    except Exception as e:
        print(f"[-] Connection error with {client_ip}: {e}")
    finally:
        print(f"[-] Client disconnected: {client_ip}")


async def main():
    print("====================================================")
    print("      SWAYAM HEALTH LOCAL INFERENCE SERVER          ")
    print("     Sign Language Continuous Sentence Model        ")
    print("====================================================")
    print(f"Running WebSocket Server on: ws://{HOST}:{PORT}")
    print("Press Ctrl+C to stop the server.")
    print("----------------------------------------------------")
    
    try:
        async with websockets.serve(handle_connection, HOST, PORT):
            await asyncio.Future()  # run forever
    except ImportError:
        print("\n[CRITICAL ERROR] Python 'websockets' package is missing.")
        print("To fix this, please run:")
        print("    pip install websockets")
        print("Then restart the script.")
    except Exception as e:
        print(f"\n[-] Server failed to start: {e}")

if __name__ == "__main__":
    # Ensure websockets library is installed
    try:
        import websockets
    except ImportError:
        print("[!] Library 'websockets' not found. Installing via subprocess...")
        import subprocess
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
        import websockets
        
    asyncio.run(main())
