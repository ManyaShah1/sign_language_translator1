const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const WebSocket = require('ws');
const localtunnel = require('localtunnel');

// Load environment variables from .env file if it exists
function loadEnv() {
    const envPath = path.join(__dirname, '.env');
    if (fs.existsSync(envPath)) {
        const envContent = fs.readFileSync(envPath, 'utf8');
        envContent.split(/\r?\n/).forEach(line => {
            if (line.trim().startsWith('#') || !line.trim()) return;
            const match = line.match(/^\s*([\w.-]+)\s*=\s*(.*)?\s*$/);
            if (match) {
                const key = match[1];
                let value = match[2] || '';
                if (value.startsWith('"') && value.endsWith('"')) {
                    value = value.slice(1, -1);
                } else if (value.startsWith("'") && value.endsWith("'")) {
                    value = value.slice(1, -1);
                }
                process.env[key] = value.trim();
            }
        });
    }
}
loadEnv();


const PORT = 8769; // Port for Node.js gateway
const PYTHON_PORT = 8768; // Port of the Python inference server

// 1. Find Python executable
function getPythonExecutable() {
    const customPath = 'C:\\Users\\tofik\\AppData\\Local\\Python\\bin\\python.exe';
    if (fs.existsSync(customPath)) {
        return customPath;
    }
    return 'python'; // Fallback to system python
}

// 2. Start Python server as child process
console.log('[*] Starting local Python inference server...');
const pythonScript = path.join(__dirname, '..', 'python_server', 'server.py');
const pythonExec = getPythonExecutable();

console.log(`[*] Spawning Python: ${pythonExec} with script: ${pythonScript}`);

const pythonProcess = spawn(pythonExec, [pythonScript], {
    cwd: path.join(__dirname, '..', 'python_server'),
    stdio: 'pipe',
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUNBUFFERED: '1' }
});

pythonProcess.stdout.on('data', (data) => {
    process.stdout.write(`[Python] ${data}`);
});

pythonProcess.stderr.on('data', (data) => {
    process.stderr.write(`[Python Error] ${data}`);
});

pythonProcess.on('close', (code) => {
    console.log(`[!] Python process exited with code ${code}`);
    process.exit(code);
});

// 3. Start Node.js WebSocket gateway server
const wss = new WebSocket.Server({ port: PORT });
console.log(`[✓] Node.js WebSocket Gateway running on ws://localhost:${PORT}`);

wss.on('connection', (wsClient, req) => {
    const clientIp = req.socket.remoteAddress;
    console.log(`[+] Client connected to gateway from: ${clientIp}`);

    // Create a connection to the local Python server
    const pySocketUrl = `ws://localhost:${PYTHON_PORT}`;
    let pySocket = null;
    let messageQueue = [];

    function connectToPython() {
        pySocket = new WebSocket(pySocketUrl);

        pySocket.on('open', () => {
            console.log(`[✓] Gateway connected to local Python server for client ${clientIp}`);
            // Flush any queued messages
            while (messageQueue.length > 0) {
                const msg = messageQueue.shift();
                if (pySocket.readyState === WebSocket.OPEN) {
                    pySocket.send(msg);
                }
            }
        });

        pySocket.on('message', (message) => {
            // Forward message from Python to the client
            if (wsClient.readyState === WebSocket.OPEN) {
                wsClient.send(message.toString());
            }
        });

        pySocket.on('error', (err) => {
            console.error(`[-] Python socket error for client ${clientIp}:`, err.message);
        });

        pySocket.on('close', () => {
            console.log(`[-] Python socket closed for client ${clientIp}`);
            wsClient.close();
        });
    }

    // Connect to python server
    connectToPython();

    wsClient.on('message', (message) => {
        // Forward message from client to Python
        if (pySocket && pySocket.readyState === WebSocket.OPEN) {
            pySocket.send(message.toString());
        } else {
            // Queue messages if Python socket is not ready yet
            messageQueue.push(message.toString());
        }
    });

    wsClient.on('error', (err) => {
        console.error(`[-] Client socket error from ${clientIp}:`, err.message);
    });

    wsClient.on('close', () => {
        console.log(`[-] Client disconnected from gateway: ${clientIp}`);
        if (pySocket) {
            pySocket.close();
        }
    });
});

let ngrokProcess = null;

// 4. Initialize Secure Tunnel
(async () => {
    const useNgrok = !!process.env.NGROK_AUTHTOKEN;
    
    if (useNgrok) {
        try {
            const secureWssUrl = await startNgrokDirect();
            console.log('\n====================================================');
            console.log('      NGROK SECURE TUNNEL ESTABLISHED SUCCESSFULLY');
            console.log(`      Your remote WSS endpoint is:\n`);
            console.log(`      ${secureWssUrl}`);
            console.log('\n      Use this URL in your remote Web Application!');
            console.log('====================================================\n');
        } catch (err) {
            console.error('[-] Failed to create ngrok tunnel:', err.message);
            console.log('[*] Falling back to localtunnel...');
            await startLocaltunnel();
        }
    } else {
        await startLocaltunnel();
    }

    async function startNgrokDirect() {
        console.log('[*] Initializing secure tunnel via ngrok CLI...');
        return new Promise((resolve, reject) => {
            const ngrokBin = path.join(__dirname, 'node_modules', 'ngrok', 'bin', 'ngrok.exe');
            if (process.env.NGROK_AUTHTOKEN) {
                try {
                    const { execSync } = require('child_process');
                    execSync(`"${ngrokBin}" config add-authtoken ${process.env.NGROK_AUTHTOKEN}`, { stdio: 'ignore' });
                } catch (e) {
                    console.error('[-] Warning: Failed to configure authtoken via ngrok CLI:', e.message);
                }
            }

            ngrokProcess = spawn(ngrokBin, ['http', PORT, '--log=stdout'], {
                cwd: __dirname,
                windowsHide: true
            });

            let resolved = false;

            ngrokProcess.stdout.on('data', (data) => {
                const output = data.toString();
                const lines = output.split(/\r?\n/);
                for (const line of lines) {
                    if (line.includes('started tunnel') && line.includes('url=')) {
                        const match = line.match(/url=([^\s]+)/);
                        if (match && match[1]) {
                            const tunnelUrl = match[1];
                            const secureWssUrl = tunnelUrl.replace(/^http/, 'ws');
                            resolved = true;
                            resolve(secureWssUrl);
                        }
                    }
                    if (line.includes('err=')) {
                        console.log(`[ngrok Log] ${line}`);
                    }
                }
            });

            ngrokProcess.stderr.on('data', (data) => {
                console.error(`[ngrok Error] ${data.toString()}`);
            });

            ngrokProcess.on('close', (code) => {
                if (!resolved) {
                    reject(new Error(`ngrok exited with code ${code}`));
                }
            });
        });
    }

    async function startLocaltunnel() {
        console.log('[*] Initializing secure tunnel via localtunnel...');
        try {
            const tunnel = await localtunnel({ port: PORT });
            const secureWssUrl = tunnel.url.replace(/^http/, 'ws');
            
            console.log('\n====================================================');
            console.log('      SECURE TUNNEL ESTABLISHED SUCCESSFULLY');
            console.log(`      Your remote WSS endpoint is:\n`);
            console.log(`      ${secureWssUrl}`);
            console.log('\n      Use this URL in your remote Web Application!');
            console.log('====================================================\n');

            tunnel.on('close', () => {
                console.log('[!] Tunnel closed');
            });
            
            tunnel.on('error', (err) => {
                console.error('[-] Tunnel error:', err);
            });
        } catch (err) {
            console.error('[-] Failed to create localtunnel:', err.message);
            console.log('[!] You can still access the server locally on ws://localhost:' + PORT);
        }
    }
})();

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('\n[-] Stopping Node.js gateway and Python subprocess...');
    if (pythonProcess) {
        pythonProcess.kill();
    }
    if (ngrokProcess) {
        ngrokProcess.kill();
    }
    process.exit(0);
});
