import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from notification_manager import AgentType, Notification, NotificationManager, NotificationPriority

app = FastAPI(title="Notification Service")
notification_manager = NotificationManager()

class NotificationCreate(BaseModel):
    source: str
    content: str
    priority: NotificationPriority
    target_agents: List[AgentType]
    metadata: dict = {}

@app.post("/notifications", response_model=dict)
async def create_notification(notification: NotificationCreate):
    """Create a new notification."""
    notification_data = notification.dict()
    notification_data["id"] = str(uuid.uuid4())
    notification_data["timestamp"] = datetime.utcnow()
    
    try:
        notification_id = notification_manager.add_notification(notification_data)
        return {"status": "success", "notification_id": notification_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/notifications/{agent_type}/pending")
async def get_pending_notifications(agent_type: AgentType):
    """Get pending notifications for a specific agent type."""
    try:
        notifications = notification_manager.get_pending_notifications(agent_type)
        return {"notifications": [n.dict() for n in notifications]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/notifications/{notification_id}/processed")
async def mark_notification_processed(notification_id: str, result: Optional[dict] = None):
    """Mark a notification as processed."""
    try:
        notification_manager.mark_notification_processed(notification_id, result)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/notifications/{notification_id}/status")
async def get_notification_status(notification_id: str):
    """Get the status of a specific notification."""
    try:
        status = notification_manager.get_notification_status(notification_id)
        return status
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 