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
import { VaultClient } from './vault-client';

const vaultClient = new VaultClient(process.env.VAULT_URL || 'http://localhost:3000');

dotenv.config();

const AGENT_FOLDER = "agent"
// Replace Python interpreter setup with path configuration
const VENV_PYTHON = path.join(__dirname, `../${AGENT_FOLDER}/.venv/bin/python`);
const MAIN_SCRIPT = `scripts.main`

// Express server
const app = express();
const port = process.env.PORT || 4999;

// WebSocket server
const wss = new WebSocketServer({ noServer: true });

// Trading session manager
const sessions: Map<string, Session> = new Map();

// Add these constants after other constants
const LOGS_DIR = path.join(__dirname, './logs');
const DB_PATH = path.join(__dirname, `../${AGENT_FOLDER}/db/trading_agent.db`);
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

// Send prompts to client
app.get('/prompts', async (req: Request, res: Response) => {
    try {
        const promptsPath = path.join(__dirname, `../${AGENT_FOLDER}/data/prompts.json`);
        const promptsData = await fs.promises.readFile(promptsPath, 'utf8');
        res.json(JSON.parse(promptsData));
    } catch (error) {
        console.error('Error reading prompts file:', error);
        res.status(500).json({
            status: 'error',
            message: 'Failed to read prompts file'
        });
    }
});

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

    // Log the initial request payload
    const initialLogEntry = {
        timestamp: new Date().toISOString(),
        type: 'request',
        payload: req.body || {}
    };
    fs.writeFileSync(logFile, JSON.stringify(initialLogEntry) + '\n');

    // Determine which script to run based on agent_type
    const scriptToRun =  MAIN_SCRIPT;

    const agentType = req.body?.agent_type;

    const agentId = req.body?.agent_id; 

    if (!scriptToRun) {
        return res.status(400).json({
            status: 'error',
            message: 'Invalid agent type, must be either "trading" or "marketing"'
        });
    }

    const pythonProcess = spawn(VENV_PYTHON, ['-m', scriptToRun, agentType, sessionId, agentId], {
        stdio: ['pipe', 'pipe', 'pipe', 'ipc'],
        env: {
            ...process.env,
            VIRTUAL_ENV: path.join(__dirname, `../${AGENT_FOLDER}/.venv`),
            PATH: `${path.join(__dirname, `../${AGENT_FOLDER}/.venv/bin`)}:${process.env.PATH}`,
            PYTHONPATH: path.join(__dirname, `../${AGENT_FOLDER}`),
        },
        cwd: path.join(__dirname, `../${AGENT_FOLDER}`)
    });

    if (!pythonProcess.stdout || !pythonProcess.stderr || !pythonProcess.stdin) {
        return res.status(500).json({
            status: 'error',
            message: 'Failed to start trading session'
        });
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

    let initReceived = false;
    let stdoutBuffer = '';
    let responseHandled = false;

    // Send initial response immediately
    res.json({
        sessionId,
        status: 'success',
        message: 'Session created successfully'
    });
    responseHandled = true;

    pythonProcess.stdout?.on('data', (data: Buffer) => {
        stdoutBuffer += data.toString();

        let newlineIndex: number;
        while ((newlineIndex = stdoutBuffer.indexOf('\n')) !== -1) {
            const line = stdoutBuffer.slice(0, newlineIndex).trim();
            stdoutBuffer = stdoutBuffer.slice(newlineIndex + 1);

            try {
                const parsed = JSON.parse(line) as PythonMessage;

                if (!initReceived) {
                    initReceived = true;
                    session.status = 'ready';
                }

                const logEntry = {
                    timestamp: new Date().toISOString(),
                    type: 'stdout',
                    data: parsed
                };

                fs.appendFileSync(session.logFilePath, JSON.stringify(logEntry) + '\n');

                broadcastToClients(session, {
                    type: 'MESSAGE',
                    data: parsed
                });
            } catch (error) {
                const logEntry = {
                    timestamp: new Date().toISOString(),
                    type: 'stdout',
                    message: line
                };

                fs.appendFileSync(session.logFilePath, JSON.stringify(logEntry) + '\n');

                broadcastToClients(session, {
                    type: 'LOG',
                    message: line
                });
            }
        }
    });

    pythonProcess.stderr?.on('data', (data: Buffer) => {
        const errorMessage = data.toString().trim();

        const logEntry = {
            timestamp: new Date().toISOString(),
            type: 'stderr',
            message: errorMessage
        };

        fs.appendFileSync(session.logFilePath, JSON.stringify(logEntry) + '\n');

        if (!initReceived && errorMessage.includes('Reset agent')) {
            initReceived = true;
            session.status = 'ready';
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
    });

    setTimeout(() => {
        if (!initReceived) {
            cleanupSession(sessionId, 500, 'Initialization timeout');
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
        
        // Signal to PM2 that the application is ready
        if (process.send) {
            process.send('ready');
        }
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