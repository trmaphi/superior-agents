import { createClient } from 'redis';
import { Session } from './types';

// Create Redis client
const redisClient = createClient({
  url: process.env.REDIS_URL || 'redis://localhost:6380',
  socket: {
    reconnectStrategy: (retries) => {
      console.log(`[Redis] Reconnection attempt ${retries}`);
      return Math.min(retries * 50, 1000);
    }
  }
});

redisClient.on('error', (err: any) => console.error('[Redis] Client Error', err));
redisClient.on('connect', () => console.log('[Redis] Connected successfully'));
redisClient.on('ready', () => console.log(`[Redis] Ready to use - ${process.env.REDIS_URL || 'redis://localhost:6380'}`));
redisClient.on('reconnecting', () => console.log('[Redis] Reconnecting...'));
redisClient.on('end', () => console.log('[Redis] Connection ended'));

// Initialize Redis connection
export async function initializeRedis() {
  if (!redisClient.isOpen) {
    await redisClient.connect();
  }
}

// Modify the sessions management
export class SessionManager {
  private static instance: SessionManager;
  private localSessions: Map<string, Session> = new Map();

  private constructor() {}

  static getInstance(): SessionManager {
    if (!SessionManager.instance) {
      SessionManager.instance = new SessionManager();
    }
    return SessionManager.instance;
  }

  async setSession(sessionId: string, session: Session): Promise<void> {
    const serializedSession = JSON.stringify({
      ...session,
      wsClients: [],
      sseClients: [],
      pendingRequests: {},
      process: null // Don't try to serialize the process
    });
    
    await redisClient.set(`session:${sessionId}`, serializedSession);
  }

  async getSession(sessionId: string): Promise<Session | null> {
    const data = await redisClient.get(`session:${sessionId}`);
    if (!data) return null;
    
    try {
      const session = JSON.parse(data);
      // Reconstruct the Set objects since they don't serialize
      session.wsClients = new Set();
      session.sseClients = new Set();
      session.pendingRequests = new Map();
      return session;
    } catch (error) {
      console.error('[Redis] Failed to parse session data:', error);
      return null;
    }
  }

  async deleteSession(sessionId: string): Promise<void> {
    await redisClient.del(`session:${sessionId}`);
  }

  async listSessions(): Promise<string[]> {
    const keys = await redisClient.keys('session:*');
    return keys.map((key: string) => key.replace('session:', ''));
  }
}

// Export singleton instance
export const sessionManager = SessionManager.getInstance();