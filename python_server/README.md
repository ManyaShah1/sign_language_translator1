# Swayam Health Local Inference Server

This is the local python server that acts as your **100% Free & Unlimited** Connectionist Temporal Classification (CTC) sequence decoder for translating continuous sign language gestures into full sentences.

## Installation

Ensure you have Python 3.7+ installed.

1. Install the required `websockets` library:
   ```bash
   pip install websockets
   ```
   *(Note: The server script will attempt to install it automatically if it is missing)*

## Running the Server

1. Open a terminal and run:
   ```bash
   python server.py
   ```
2. The server will start and output:
   ```
   ====================================================
         SWAYAM HEALTH LOCAL INFERENCE SERVER          
        Sign Language Continuous Sentence Model        
   ====================================================
   Running WebSocket Server on: ws://0.0.0.0:8765
   Press Ctrl+C to stop the server.
   ----------------------------------------------------
   ```
3. Open your Flutter application, configure the WebSocket IP to `ws://localhost:8765` (or your machine's local IP if testing on a physical phone), and toggle **Connect**.
4. The server console will output coordinate stream packets, velocity checks, and sentence classification logs in real-time.
