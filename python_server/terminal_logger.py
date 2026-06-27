import asyncio
import json
import os
import sys
import numpy as np
import websockets

PORT = 8768
DATA_DIR = "data_sequences"
TARGET_FRAMES = 45

async def log_sequence(websocket, path=None):
    # Prompt the user for the word label
    word = input("\nEnter word to log: ").strip().upper()
    if not word:
        print("[-] Invalid word.")
        os._exit(1)
        
    word_dir = os.path.join(DATA_DIR, word)
    os.makedirs(word_dir, exist_ok=True)
    
    # Auto-index samples
    existing_samples = [f for f in os.listdir(word_dir) if f.endswith(".npy")]
    sample_index = len(existing_samples)
    
    print(f"[*] Waiting for {TARGET_FRAMES} coordinate frames from Flutter app in Word Mode...")
    sequence = []
    
    async for message in websocket:
        try:
            payload = json.loads(message)
        except:
            continue
            
        if payload.get("type") != "coordinates":
            continue
            
        landmarks = payload.get("landmarks", [])
        if landmarks:
            frame_coords = []
            for lm in landmarks:
                frame_coords.extend([lm.get("x", 0.0), lm.get("y", 0.0), lm.get("z", 0.0)])
            
            if len(frame_coords) == 63:
                sequence.append(frame_coords)
                print(f"[+] Frame {len(sequence)}/{TARGET_FRAMES} logged.")
                
            if len(sequence) == TARGET_FRAMES:
                seq_arr = np.array(sequence, dtype=np.float32)
                file_path = os.path.join(word_dir, f"sample_{sample_index}.npy")
                np.save(file_path, seq_arr)
                print(f"[✓] Sequence logged successfully at: {file_path}")
                break
                
    print("[*] Closing socket listener session.")
    os._exit(0)

async def main():
    print(f"[*] Terminal logger WebSocket listener boot on ws://0.0.0.0:{PORT}...")
    async with websockets.serve(log_sequence, "0.0.0.0", PORT):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[-] Logger utility stopped.")
