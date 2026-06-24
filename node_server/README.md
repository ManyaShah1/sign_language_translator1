# Node.js Remote WebSocket Gateway Server

This server bridges your local Python Sign Language Inference Server (`python_server/server.py`) and a remote Web Application via a secure public WebSocket (`wss://`) tunnel. 

It solves the **Mixed Content** security restriction where secure remote sites (`https://`) are blocked from connecting to unsecure local endpoints (`ws://localhost` or `ws://192.168.x.x`).

## How It Works

1. Spawns your local Python inference server as a subprocess.
2. Starts a Node.js WebSocket Gateway server on port `8769`.
3. Opens a secure public tunnel via `localtunnel` to output a unique `wss://` URL.
4. Relays incoming gesture coordinate streams from the remote web application to the local Python engine, and proxies the translation results back.

## How to Run the Server

Double-click the script in your project root:
- [start.bat](file:///c:/Users/tofik/StudioProjects/sign_language_translator/node_server/start.bat)

*Note: If you do not have Node.js installed, the script will automatically download a portable version of Node.js v20.11.0 into a `portable_node/` folder inside the server directory.*

## Connecting Your Web Client

1. Run the `start.bat` script.
2. Wait for the terminal to print your secure endpoint URL. It will look like this:
   ```
   ====================================================
         SECURE TUNNEL ESTABLISHED SUCCESSFULLY
         Your remote WSS endpoint is:

         ws://xxxx.loca.lt

         Use this URL in your remote Web Application!
   ====================================================
   ```
3. Copy the URL (replacing `ws://` with `wss://` if needed, although localtunnel supports both transparently).
4. Paste this URL into the **Local Inference Server Address** field in the remote web application, and click **Connect**.
