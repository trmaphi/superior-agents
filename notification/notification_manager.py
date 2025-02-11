import json
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentType(str, Enum):
    MARKETING = "marketing"
    TRADING = "trading"
    TRADING_ASSISTED = "trading_assisted"

class NotificationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class Notification(BaseModel):
    id: str
    timestamp: datetime
    source: str
    content: str
    priority: NotificationPriority
    target_agents: List[AgentType]
    metadata: Dict = {}
    processed: bool = False
    processing_result: Optional[Dict] = None

class NotificationManager:
    def __init__(self):
        self.notifications: Dict[str, Notification] = {}
        self.agent_queues: Dict[AgentType, List[str]] = {
            agent_type: [] for agent_type in AgentType
        }
        
    def add_notification(self, notification: Union[Notification, dict]) -> str:
        """Add a new notification to the system."""
        if isinstance(notification, dict):
            notification = Notification(**notification)
            
        self.notifications[notification.id] = notification
        
        # Route notification to appropriate agent queues
        for agent_type in notification.target_agents:
            self.agent_queues[agent_type].append(notification.id)
            
        logger.info(f"Added notification {notification.id} for agents {notification.target_agents}")
        return notification.id
    
    def get_pending_notifications(self, agent_type: AgentType) -> List[Notification]:
        """Get all pending notifications for a specific agent type."""
        pending = []
        for notif_id in self.agent_queues[agent_type]:
            notification = self.notifications[notif_id]
            if not notification.processed:
                pending.append(notification)
        return pending
    
    def mark_notification_processed(self, notification_id: str, result: Dict = None) -> None:
        """Mark a notification as processed with optional result data."""
        if notification_id not in self.notifications:
            raise ValueError(f"Notification {notification_id} not found")
            
        notification = self.notifications[notification_id]
        notification.processed = True
        notification.processing_result = result
        
        # Remove from agent queues
        for queue in self.agent_queues.values():
            if notification_id in queue:
                queue.remove(notification_id)
                
        logger.info(f"Marked notification {notification_id} as processed")
    
    def get_notification_status(self, notification_id: str) -> Dict:
        """Get the current status of a notification."""
        if notification_id not in self.notifications:
            raise ValueError(f"Notification {notification_id} not found")
            
        notification = self.notifications[notification_id]
        return {
            "id": notification.id,
            "processed": notification.processed,
            "target_agents": notification.target_agents,
            "processing_result": notification.processing_result
        } 