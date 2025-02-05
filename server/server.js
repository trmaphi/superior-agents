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

// Add SSE middleware
function sseMiddleware(req, res, next) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.flushHeaders();

    // Send a ping every 30 seconds to keep the connection alive
    const pingInterval = setInterval(() => {
        res.write('event: ping\ndata: ping\n\n');
    }, 30000);

    // Clean up on client disconnect
    res.on('close', () => {
        clearInterval(pingInterval);
    });

    next();
}

// Add new SSE endpoint for session events
app.get('/sessions/:sessionId/events', sseMiddleware, (req, res) => {
    const sessionId = req.params.sessionId;
    const session = sessions.get(sessionId);
    
    if (!session) {
        res.write(`event: error\ndata: ${JSON.stringify({ message: 'Session not found' })}\n\n`);
        res.end();
        return;
    }

    // Send initial session status
    res.write(`event: status\ndata: ${JSON.stringify({
        status: session.status,
        connectedClients: session.wsClients.size
    })}\n\n`);

    // Create SSE message handler
    const sseClient = {
        send: (data) => {
            const event = data.type || 'message';
            res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
        }
    };

    // Add SSE client to session
    if (!session.sseClients) {
        session.sseClients = new Set();
    }
    session.sseClients.add(sseClient);

    // Clean up on client disconnect
    res.on('close', () => {
        if (session.sseClients) {
            session.sseClients.delete(sseClient);
        }
    });
});

// Helper functions (move these before they are used)
function cleanupSession(sessionId, code = 1000, reason = 'Session ended') {
    const session = sessions.get(sessionId);
    if (!session) return;

    // Notify WebSocket clients
    session.wsClients.forEach(client => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify({
                type: 'SESSION_END',
                reason: reason
            }));
            client.close(code, reason);
        }
    });

    // Notify SSE clients
    if (session.sseClients) {
        session.sseClients.forEach(client => {
            client.send({
                type: 'SESSION_END',
                reason: reason
            });
        });
    }

    // Cleanup process
    if (!session.process.killed) {
        session.process.stdin.end();
        session.process.kill();
    }

    sessions.delete(sessionId);
}

function broadcastToClients(session, message) {
    // Broadcast to WebSocket clients
    session.wsClients.forEach(client => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify(message));
        }
    });

    // Broadcast to SSE clients
    if (session.sseClients) {
        session.sseClients.forEach(client => {
            client.send(message);
        });
    }
}

// Create new trading session
app.post('/sessions', (req, res) => {
    const sessionId = crypto.randomUUID();
    const pythonProcess = spawn(VENV_PYTHON, [MAIN_SCRIPT], {
        stdio: ['pipe', 'pipe', 'pipe', 'ipc'],
        env: {
            ...process.env,
            VIRTUAL_ENV: path.join(__dirname, '../.venv'),
            PATH: `${path.join(__dirname, '../.venv/bin')}:${process.env.PATH}`,
            PYTHONPATH: path.join(__dirname, '..'),
        },
        cwd: path.join(__dirname, '..')
    });

    const session = {
        process: pythonProcess,
        status: 'starting',
        buffer: '',
        wsClients: new Set(),
        pendingRequests: new Map()
    };
    sessions.set(sessionId, session);

    let initReceived = false;

    // Handle process output
    pythonProcess.stdout.on('data', (data) => {
        const message = data.toString().trim();
        console.log('Python stdout:', message); // Debug log

        try {
            const parsed = JSON.parse(message);
            
            // Handle initialization message
            if (!initReceived && (parsed.type === 'INIT' || parsed.event === 'init')) {
                initReceived = true;
                session.status = 'ready';
                res.json({ 
                    sessionId,
                    status: 'success',
                    message: 'Session created successfully'
                });
                return;
            }

            // Echo message to all connected clients
            broadcastToClients(session, {
                type: 'MESSAGE',
                data: parsed
            });
        } catch (error) {
            // If it's not JSON, check if it contains initialization indicator
            if (!initReceived && message.includes('Reset agent')) {
                initReceived = true;
                session.status = 'ready';
                res.json({ 
                    sessionId,
                    status: 'success',
                    message: 'Session created successfully'
                });
                return;
            }

            // Treat as log message
            broadcastToClients(session, {
                type: 'LOG',
                message: message
            });
        }
    });

    // Handle errors and echo them to clients
    pythonProcess.stderr.on('data', (data) => {
        const errorMessage = data.toString().trim();
        console.log('Python stderr:', errorMessage); // Debug log

        // Check for initialization in stderr as well
        if (!initReceived && errorMessage.includes('Reset agent')) {
            initReceived = true;
            session.status = 'ready';
            res.json({ 
                sessionId,
                status: 'success',
                message: 'Session created successfully'
            });
            return;
        }

        broadcastToClients(session, {
            type: 'LOG', // Changed from ERROR to LOG since these are actually INFO messages
            message: errorMessage
        });
    });

    pythonProcess.on('error', (error) => {
        console.error('Process failed:', error);
        broadcastToClients(session, {
            type: 'ERROR',
            message: error.message
        });
        cleanupSession(sessionId, 500, 'Process startup failed');
        if (!res.headersSent) {
            res.status(500).json({ 
                status: 'error',
                message: 'Failed to start trading session'
            });
        }
    });

    // Increase timeout to 30 seconds
    setTimeout(() => {
        if (!initReceived) {
            cleanupSession(sessionId, 500, 'Initialization timeout');
            if (!res.headersSent) {
                res.status(500).json({ 
                    status: 'error',
                    message: 'Session initialization timeout'
                });
            }
        }
    }, 30000); // Increased from 10000 to 30000
});

// Get session status endpoint
app.get('/sessions/:sessionId', (req, res) => {
    const session = sessions.get(req.params.sessionId);
    if (!session) {
        return res.status(404).json({
            status: 'error',
            message: 'Session not found'
        });
    }
    
    res.json({
        status: 'success',
        sessionStatus: session.status,
        connectedClients: session.wsClients.size
    });
});

// WebSocket connection handler
wss.on('connection', (ws, req) => {
    const sessionId = new URL(req.url, `http://${req.headers.host}`).searchParams.get('sessionId');
    const session = sessions.get(sessionId);

    if (!session || session.status !== 'ready') {
        ws.close(4001, 'Invalid or not ready session');
        return;
    }

    session.wsClients.add(ws);

    // Send initial connection success message
    ws.send(JSON.stringify({
        type: 'CONNECTION_STATUS',
        status: 'connected',
        sessionId
    }));

    ws.on('message', (message) => {
        try {
            const { action, params = {} } = JSON.parse(message);
            const correlationId = crypto.randomUUID();
            
            const command = JSON.stringify({ 
                action, 
                params, 
                correlationId 
            }) + '\n';
            
            session.process.stdin.write(command);
            session.pendingRequests.set(correlationId, ws);
        } catch (error) {
            ws.send(JSON.stringify({
                type: 'ERROR',
                message: error.message
            }));
        }
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

// WebSocket upgrade
const server = app.listen(port, () => {
    console.log(`Server running on port ${port}`);
});

server.on('upgrade', (request, socket, head) => {
    wss.handleUpgrade(request, socket, head, (ws) => {
        wss.emit('connection', ws, request);
    });
});