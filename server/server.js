const express = require('express');
const WebSocket = require('ws');
const { spawn } = require('child_process');
const path = require('path');
const dotenv = require('dotenv');
const crypto = require('crypto');

dotenv.config();

// Replace Python interpreter setup with path configuration
const VENV_PYTHON = path.join(__dirname, '../.venv/bin/python');
const MAIN_SCRIPT = path.join(__dirname, '../scripts/main_trader_2.py');

// Express server
const app = express();
const port = process.env.PORT || 3001;

// WebSocket server
const wss = new WebSocket.Server({ noServer: true });

// Trading session manager
const sessions = new Map();

app.use(express.json());

// API endpoints
app.post('/sessions', (req, res) => {
    const sessionId = crypto.randomUUID();
    
    // Spawn Python process with venv and correct working directory
    const pythonProcess = spawn(VENV_PYTHON, [MAIN_SCRIPT], {
        stdio: ['pipe', 'pipe', process.stdout, 'ipc'],  // Redirect stderr to stdout
        env: {
            ...process.env,
            VIRTUAL_ENV: path.join(__dirname, '../.venv'),
            PATH: `${path.join(__dirname, '../.venv/bin')}:${process.env.PATH}`
        },
        cwd: path.join(__dirname, '..') // Set working directory to project root
    });

    let buffer = '';
    
    pythonProcess.stdout.on('data', (data) => {
        buffer += data.toString();
        // Process complete JSON messages
        while (true) {
            const start = buffer.indexOf('{');
            const end = buffer.indexOf('}\n');
            if (start === -1 || end === -1) break;
            
            const message = buffer.slice(start, end + 1);
            buffer = buffer.slice(end + 2);
            
            try {
                const { type, payload } = JSON.parse(message);
                if (type === 'INIT') {
                    sessions.set(sessionId, {
                        process: pythonProcess,
                        status: 'ready',
                        wsClients: new Set(),
                        pendingRequests: new Map()
                    });
                    res.json({ sessionId });
                }
            } catch (e) {
                console.error('Failed to parse message:', message);
            }
        }
    });

    pythonProcess.on('error', (error) => {
        console.error('Process failed:', error);
        res.status(500).json({ error: 'Failed to start process' });
    });

    pythonProcess.on('exit', (code) => {
        console.log(`Python process exited with code ${code}`);
        sessions.delete(sessionId);
    });
});

// WebSocket upgrade
const server = app.listen(port, () => {
    console.log(`Server running on port ${port}`);
});

server.on('upgrade', (request, socket, head) => {
    wss.handleUpgrade(request, socket, head, (ws) => {
        wss.emit('connection', ws, request);
    });
});

// WebSocket communication
wss.on('connection', (ws, req) => {
    const sessionId = new URL(req.url, `http://${req.headers.host}`).searchParams.get('sessionId');
    const session = sessions.get(sessionId);

    if (!session) {
        ws.close(4001, 'Invalid session ID');
        return;
    }

    session.wsClients.add(ws);
    
    ws.on('message', async (message) => {
        const { action, params, correlationId } = JSON.parse(message);
        const pythonProcess = session.process;
        
        // Send command to Python process
        const command = JSON.stringify({
            action,
            params,
            correlationId
        }) + '\n';
        
        pythonProcess.stdin.write(command);
        
        // Store pending request
        session.pendingRequests.set(correlationId, ws);
    });

    // Handle Python process output
    session.process.stdout.on('data', (data) => {
        buffer += data.toString();
        while (true) {
            const end = buffer.indexOf('}\n');
            if (end === -1) break;
            
            const message = buffer.slice(0, end + 1);
            buffer = buffer.slice(end + 2);
            
            try {
                const { correlationId, result, error } = JSON.parse(message);
                const client = session.pendingRequests.get(correlationId);
                
                if (client) {
                    client.send(JSON.stringify({
                        status: error ? 'error' : 'success',
                        correlationId,
                        result,
                        error
                    }));
                    session.pendingRequests.delete(correlationId);
                }
            } catch (e) {
                console.error('Failed to process response:', message);
            }
        }
    });

    ws.on('close', () => {
        session.wsClients.delete(ws);
    });
});