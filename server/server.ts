import express, { Request, Response, NextFunction } from 'express';
import { WebSocket, WebSocketServer } from 'ws';
import { spawn } from 'child_process';
import path from 'path';
import dotenv from 'dotenv';
import crypto from 'crypto';
import { Session, SSEClient, PythonMessage, WebSocketMessage } from './types';

dotenv.config();

// Replace Python interpreter setup with path configuration
const VENV_PYTHON = path.join(__dirname, '../.venv/bin/python');
const MAIN_SCRIPT = path.join(__dirname, '../scripts/main_trader_2.py');

// Express server
const app = express();
const port = process.env.PORT || 4999;

// WebSocket server
const wss = new WebSocketServer({ noServer: true });

// Trading session manager
const sessions: Map<string, Session> = new Map();

app.use(express.json());

function sseMiddleware(req: Request, res: Response, next: NextFunction): void {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.flushHeaders();

    const pingInterval = setInterval(() => {
        res.write('event: ping\ndata: ping\n\n');
    }, 30000);

    res.on('close', () => {
        clearInterval(pingInterval);
    });

    next();
}

app.get('/sessions/:sessionId/events', sseMiddleware, (req: Request, res: Response) => {
    const sessionId = req.params.sessionId;
    const session = sessions.get(sessionId);
    
    if (!session) {
        res.write(`event: error\ndata: ${JSON.stringify({ message: 'Session not found' })}\n\n`);
        res.end();
        return;
    }

    res.write(`event: status\ndata: ${JSON.stringify({
        status: session.status,
        connectedClients: session.wsClients.size
    })}\n\n`);

    const sseClient: SSEClient = {
        send: (data: any) => {
            const event = data.type || 'message';
            res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
        }
    };

    if (!session.sseClients) {
        session.sseClients = new Set();
    }
    session.sseClients.add(sseClient);

    res.on('close', () => {
        if (session.sseClients) {
            session.sseClients.delete(sseClient);
        }
    });
});

function cleanupSession(sessionId: string, code: number = 1000, reason: string = 'Session ended'): void {
    const session = sessions.get(sessionId);
    if (!session) return;

    session.wsClients.forEach(client => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify({
                type: 'SESSION_END',
                reason: reason
            }));
            client.close(code, reason);
        }
    });

    if (session.sseClients) {
        session.sseClients.forEach(client => {
            client.send({
                type: 'SESSION_END',
                reason: reason
            });
        });
    }

    if (!session.process.killed) {
        if (session.process.stdin) {
            session.process.stdin.end();
        }
        session.process.kill();
    }

    sessions.delete(sessionId);
}

function broadcastToClients(session: Session, message: any): void {
    session.wsClients.forEach(client => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify(message));
        }
    });

    if (session.sseClients) {
        session.sseClients.forEach(client => {
            client.send(message);
        });
    }
}

app.post('/sessions', (req: Request, res: Response) => {
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

    // Early validation of process streams
    if (!pythonProcess.stdout || !pythonProcess.stderr || !pythonProcess.stdin) {
        console.error('Failed to create process with required streams');
        res.status(500).json({
            status: 'error',
            message: 'Failed to start trading session'
        });
        return;
    }

    const session: Session = {
        process: pythonProcess,
        status: 'starting',
        wsClients: new Set(),
        pendingRequests: new Map()
    };
    sessions.set(sessionId, session);

    let initReceived = false;
    let stdoutBuffer = '';

    pythonProcess.stdout?.on('data', (data: Buffer) => {
        stdoutBuffer += data.toString();
        let newlineIndex: number;
        while ((newlineIndex = stdoutBuffer.indexOf('\n')) !== -1) {
            const line = stdoutBuffer.slice(0, newlineIndex).trim();
            stdoutBuffer = stdoutBuffer.slice(newlineIndex + 1);
            console.log('[stdout]:', line);
            
            try {
                const parsed = JSON.parse(line) as PythonMessage;
                if (!initReceived && (parsed.type === 'INIT' || parsed.event === 'init')) {
                    initReceived = true;
                    session.status = 'ready';
                    res.json({ 
                        sessionId, 
                        status: 'success', 
                        message: 'Session created successfully' 
                    });
                }
                broadcastToClients(session, {
                    type: 'MESSAGE',
                    data: parsed
                });
            } catch (error) {
                if (!initReceived && line.includes('Reset agent')) {
                    initReceived = true;
                    session.status = 'ready';
                    res.json({ 
                        sessionId, 
                        status: 'success', 
                        message: 'Session created successfully' 
                    });
                }
                broadcastToClients(session, {
                    type: 'LOG',
                    message: line
                });
            }
        }
    });

    pythonProcess.stderr?.on('data', (data: Buffer) => {
        const errorMessage = data.toString().trim();
        console.log('Python stderr:', errorMessage);

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
            type: 'LOG',
            message: errorMessage
        });
    });

    pythonProcess.on('error', (error: Error) => {
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
    }, 30000);
});

app.get('/sessions/:sessionId', (req: Request, res: Response) => {
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

wss.on('connection', (ws: WebSocket, req: Request) => {
    const url = new URL(req.url!, `http://${req.headers.host}`);
    const sessionId = url.searchParams.get('sessionId');
    
    if (!sessionId) {
        ws.close(4001, 'Session ID required');
        return;
    }

    const session = sessions.get(sessionId);

    if (!session || session.status !== 'ready') {
        ws.close(4001, 'Invalid or not ready session');
        return;
    }

    session.wsClients.add(ws);

    ws.send(JSON.stringify({
        type: 'CONNECTION_STATUS',
        status: 'connected',
        sessionId
    }));

    let buffer = '';

    ws.on('message', (message: Buffer | ArrayBuffer | Buffer[]) => {
        try {
            const { action, params = {} }: WebSocketMessage = JSON.parse(message.toString());
            const correlationId = crypto.randomUUID();
            
            const command = JSON.stringify({ 
                action, 
                params, 
                correlationId 
            }) + '\n';
            
            if (session.process.stdin) {
                session.process.stdin.write(command);
                session.pendingRequests.set(correlationId, ws);
            } else {
                ws.send(JSON.stringify({
                    type: 'ERROR',
                    message: 'Process stdin not available'
                }));
            }
        } catch (error) {
            ws.send(JSON.stringify({
                type: 'ERROR',
                message: error instanceof Error ? error.message : 'Unknown error'
            }));
        }
    });

    if (session.process.stdout) {
        session.process.stdout.on('data', (data: Buffer) => {
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
    }

    ws.on('close', () => {
        session.wsClients.delete(ws);
    });
});

const server = app.listen(port, () => {
    console.log(`Server running on port ${port}`);
});

server.on('upgrade', (request: Request, socket: any, head: Buffer) => {
    wss.handleUpgrade(request, socket, head, (ws) => {
        wss.emit('connection', ws, request);
    });
});

app.use(express.static(path.join(__dirname, 'static'))); 