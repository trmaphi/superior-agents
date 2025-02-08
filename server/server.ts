import express, { Request, Response, NextFunction } from 'express';
import { WebSocket, WebSocketServer } from 'ws';
import { spawn } from 'child_process';
import path from 'path';
import dotenv from 'dotenv';
import crypto from 'crypto';
import { Session, SSEClient, PythonMessage, WebSocketMessage } from './types';
import fs from 'fs';
import sqlite3 from 'sqlite3';
import { Database, open } from 'sqlite';
import cors from 'cors';

dotenv.config();

// Replace Python interpreter setup with path configuration
const VENV_PYTHON = path.join(__dirname, '../.venv/bin/python');
const MAIN_SCRIPT = path.join(__dirname, '../scripts/main_trader.py');
const MARKETING_SCRIPT = path.join(__dirname, '../scripts/main_marketing.py');

// Express server
const app = express();
const port = process.env.PORT || 4999;

// WebSocket server
const wss = new WebSocketServer({ noServer: true });

// Trading session manager
const sessions: Map<string, Session> = new Map();

// Add these constants after other constants
const LOGS_DIR = path.join(__dirname, './logs');
const DB_PATH = path.join(__dirname, '../db/trading_agent.db');
let db: Database;

// Create logs directory if it doesn't exist
if (!fs.existsSync(LOGS_DIR)) {
    fs.mkdirSync(LOGS_DIR, { recursive: true });
}

// Add CORS middleware before other middleware and routes
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

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

app.post('/sessions/:sessionId/push', express.json(), (req, res) => {
    const sessionId = req.params.sessionId;
    const session = sessions.get(sessionId);

    if (!session) {
        return res.status(404).json({
            status: 'error',
            message: 'Session not found'
        });
    }

    console.log('Pushing log entry:', req.body);

    try {
        // Parse the message if it's a string
        const message = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;

        const logEntry = {
            timestamp: new Date().toISOString(),
            type: 'stdout',
            message: message
        };

        // Write to log file in JSONL format
        fs.appendFileSync(session.logFilePath, JSON.stringify(logEntry) + '\n');

        broadcastToClients(session, {
            type: 'LOG',
            message: message
        });

        res.json({
            status: 'success',
            message: 'Log entry pushed successfully'
        });
    } catch (error) {
        res.status(500).json({
            status: 'error',
            message: 'Failed to push log entry'
        });
    }
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

    // Optionally remove log file (comment out if you want to keep logs)
    // try {
    //     fs.unlinkSync(session.logFilePath);
    // } catch (error) {
    //     console.error(`Error removing log file: ${error}`);
    // }

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

// Add this initialization before the Express routes
async function initializeDatabase() {
    try {
        db = await open({
            filename: DB_PATH,
            driver: sqlite3.Database
        });
        console.log('Successfully connected to SQLite database');
    } catch (error) {
        console.error('Failed to connect to database:', error);
        process.exit(1);
    }
}

app.post('/sessions', (req: Request, res: Response) => {
    const sessionId = crypto.randomUUID();
    const logFile = path.join(LOGS_DIR, `${sessionId}.jsonl`);

    // Log the initial request payload with proper body parsing
    const initialLogEntry = {
        timestamp: new Date().toISOString(),
        type: 'request',
        payload: req.body || {}  // Ensure payload is never undefined
    };
    fs.writeFileSync(logFile, JSON.stringify(initialLogEntry) + '\n');

    // Determine which script to run based on agent_type
    const scriptToRun = (req.body?.agent_type === 'trading') ? MAIN_SCRIPT : MARKETING_SCRIPT;

    if (!scriptToRun) {
        res.status(400).json({
            status: 'error',
            message: 'Invalid agent type, must be either "trading" or "marketing"'
        });
        return;
    }

    const pythonProcess = spawn(VENV_PYTHON, [scriptToRun, sessionId], {
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
        pendingRequests: new Map(),
        sseClients: new Set(),
        logFilePath: logFile
    };
    sessions.set(sessionId, session);
    console.log('Session created:', session);

    let initReceived = false;
    console.log('Init received:', initReceived);
    let stdoutBuffer = '';
    
    console.log('Stdout buffer:', stdoutBuffer);
    res.json({
        sessionId,
        status: 'success',
        message: 'Session created successfully'
    });
    

    pythonProcess.stdout?.on('data', (data: Buffer) => {
        console.log('Received stdout data');
        stdoutBuffer += data.toString();
        console.log('Updated stdout buffer:', stdoutBuffer);
        
        // Set session as ready early
        if (!initReceived) {
            console.log('Setting initial session status to ready');
            initReceived = true;
            session.status = 'ready';
            console.log('Session status updated to:', session.status);
            res.json({
                sessionId,
                status: 'success',
                message: 'Session created successfully'
            });
            console.log('Sent success response to client');
        }

        let newlineIndex: number;
        while ((newlineIndex = stdoutBuffer.indexOf('\n')) !== -1) {
            const line = stdoutBuffer.slice(0, newlineIndex).trim();
            console.log('Processing line:', line);
            stdoutBuffer = stdoutBuffer.slice(newlineIndex + 1);
            console.log('Updated buffer after processing:', stdoutBuffer);

            try {
                const parsed = JSON.parse(line) as PythonMessage;
                console.log('Successfully parsed JSON:', parsed);

                const logEntry = {
                    timestamp: new Date().toISOString(),
                    type: 'stdout',
                    data: parsed
                };
                console.log('Created log entry:', logEntry);

                // Write to log file in JSONL format
                fs.appendFileSync(session.logFilePath, JSON.stringify(logEntry) + '\n');
                console.log('Wrote log entry to file');

                broadcastToClients(session, {
                    type: 'MESSAGE',
                    data: parsed
                });
                console.log('Broadcasted message to clients');
            } catch (error) {
                console.log('Failed to parse JSON, treating as plain text');
                const logEntry = {
                    timestamp: new Date().toISOString(),
                    type: 'stdout',
                    message: line
                };

                // Write to log file in JSONL format
                fs.appendFileSync(session.logFilePath, JSON.stringify(logEntry) + '\n');
                console.log('Wrote plain text log entry to file');

                broadcastToClients(session, {
                    type: 'LOG',
                    message: line
                });
                console.log('Broadcasted plain text message to clients');
            }
        }
    });

    pythonProcess.stderr?.on('data', (data: Buffer) => {
        const errorMessage = data.toString().trim();
        console.log('Python stderr:', errorMessage);

        const logEntry = {
            timestamp: new Date().toISOString(),
            type: 'stderr',
            message: errorMessage
        };

        // Write to log file in JSONL format
        fs.appendFileSync(session.logFilePath, JSON.stringify(logEntry) + '\n');

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

app.get('/sessions/:sessionId/logs', sseMiddleware, (req: Request, res: Response) => {
    const sessionId = req.params.sessionId;
    const session = sessions.get(sessionId);

    if (!session) {
        res.write(`event: error\ndata: ${JSON.stringify({ message: 'Session not found' })}\n\n`);
        res.end();
        return;
    }

    // Send initial status
    res.write(`event: status\ndata: ${JSON.stringify({
        status: session.status,
        connectedClients: session.wsClients.size
    })}\n\n`);

    // Send existing logs
    try {
        const logs = fs.readFileSync(session.logFilePath, 'utf8');
        res.write(`event: logs\ndata: ${JSON.stringify({ logs })}\n\n`);
    } catch (error) {
        console.error(`Error reading log file: ${error}`);
        res.write(`event: error\ndata: ${JSON.stringify({ message: 'Error reading logs' })}\n\n`);
    }

    // Watch for new logs
    const watcher = fs.watch(session.logFilePath, (eventType) => {
        if (eventType === 'change') {
            try {
                const newLogs = fs.readFileSync(session.logFilePath, 'utf8');
                res.write(`event: logs\ndata: ${JSON.stringify({ logs: newLogs })}\n\n`);
            } catch (error) {
                console.error(`Error reading log file: ${error}`);
            }
        }
    });

    // Cleanup on connection close
    res.on('close', () => {
        watcher.close();
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

// Initialize the database when starting the server
initializeDatabase().then(() => {
    const server = app.listen(port, () => {
        console.log(`Server running on port ${port}`);
    });

    server.on('upgrade', (request: Request, socket: any, head: Buffer) => {
        wss.handleUpgrade(request, socket, head, (ws) => {
            wss.emit('connection', ws, request);
        });
    });

    app.use(express.static(path.join(__dirname, 'static')));
}).catch(error => {
    console.error('Failed to start server:', error);
}); 