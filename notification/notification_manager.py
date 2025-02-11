import json
import logging
from datetime import datetime
import sqlite3
import os
import uuid
from typing import List, Optional

from models import NotificationCreate, NotificationUpdate, NotificationResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotificationManager:
    def __init__(self, db_path: str = "notifications.db"):
        """Initialize notification manager with database support."""
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        """Initialize the SQLite database and create necessary tables."""
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    short_desc TEXT NOT NULL,
                    long_desc TEXT NOT NULL,
                    notification_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
            """)
            conn.commit()
    
    def create_notification(self, notification: NotificationCreate) -> str:
        """Create a new notification."""
        notification_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO notifications 
                (id, source, short_desc, long_desc, notification_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    notification_id,
                    notification.source,
                    notification.short_desc,
                    notification.long_desc,
                    notification.notification_date,
                    created_at
                )
            )
            conn.commit()
            
        logger.info(f"Created notification {notification_id}")
        return notification_id
    
    def update_notification(self, notification: NotificationUpdate) -> bool:
        """Update an existing notification."""
        updated_at = datetime.utcnow().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE notifications 
                SET source = ?, short_desc = ?, long_desc = ?, 
                    notification_date = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    notification.source,
                    notification.short_desc,
                    notification.long_desc,
                    notification.notification_date,
                    updated_at,
                    notification.id
                )
            )
            conn.commit()
            
            if cursor.rowcount == 0:
                logger.error(f"Notification {notification.id} not found")
                return False
                
        logger.info(f"Updated notification {notification.id}")
        return True
    
    def get_notification(self, notification_id: str) -> Optional[NotificationResponse]:
        """Get a specific notification by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM notifications WHERE id = ?",
                (notification_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
                
            return NotificationResponse(
                id=row[0],
                source=row[1],
                short_desc=row[2],
                long_desc=row[3],
                notification_date=row[4],
                created_at=datetime.fromisoformat(row[5]),
                updated_at=datetime.fromisoformat(row[6]) if row[6] else None
            )
    
    def get_all_notifications(self) -> List[NotificationResponse]:
        """Get all notifications."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM notifications")
            notifications = []
            
            for row in cursor.fetchall():
                notifications.append(NotificationResponse(
                    id=row[0],
                    source=row[1],
                    short_desc=row[2],
                    long_desc=row[3],
                    notification_date=row[4],
                    created_at=datetime.fromisoformat(row[5]),
                    updated_at=datetime.fromisoformat(row[6]) if row[6] else None
                ))
                
            return notifications 