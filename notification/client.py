import httpx
from typing import Dict, List, Optional

from notification_manager import AgentType, NotificationPriority

class NotificationClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize notification client with base URL of the notification service."""
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient()
    
    async def create_notification(
        self,
        source: str,
        content: str,
        priority: NotificationPriority,
        target_agents: List[AgentType],
        metadata: Optional[Dict] = None
    ) -> str:
        """Create a new notification."""
        url = f"{self.base_url}/notifications"
        data = {
            "source": source,
            "content": content,
            "priority": priority,
            "target_agents": target_agents,
            "metadata": metadata or {}
        }
        
        response = await self.client.post(url, json=data)
        response.raise_for_status()
        return response.json()["notification_id"]
    
    async def get_pending_notifications(self, agent_type: AgentType) -> List[Dict]:
        """Get pending notifications for an agent type."""
        url = f"{self.base_url}/notifications/{agent_type}/pending"
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()["notifications"]
    
    async def mark_notification_processed(
        self,
        notification_id: str,
        result: Optional[Dict] = None
    ) -> None:
        """Mark a notification as processed with optional result data."""
        url = f"{self.base_url}/notifications/{notification_id}/processed"
        response = await self.client.post(url, json={"result": result} if result else {})
        response.raise_for_status()
    
    async def get_notification_status(self, notification_id: str) -> Dict:
        """Get the status of a notification."""
        url = f"{self.base_url}/notifications/{notification_id}/status"
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose() 