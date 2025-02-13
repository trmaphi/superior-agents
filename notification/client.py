import logging
from datetime import datetime
from typing import Optional

import httpx
from models import NotificationCreate

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotificationClient:
    def __init__(self, base_url: str = "https://superior-crud-api.fly.dev"):
        """Initialize notification client."""
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "x-api-key": "ccm2q324t1qv1eulq894",
            "Content-Type": "application/json"
        }
        self.client = httpx.AsyncClient(base_url=self.base_url, headers=self.headers)
        
    async def create_notification(
        self,
        source: str,
        short_desc: str,
        long_desc: str,
        notification_date: Optional[str] = None
    ) -> int:
        """Create a new notification."""
        if notification_date is None:
            notification_date = datetime.utcnow().isoformat()
            
        notification = NotificationCreate(
            source=source,
            short_desc=short_desc,
            long_desc=long_desc,
            notification_date=notification_date
        )
        
        try:
            response = await self.client.post(
                "/api_v1/notification/create",
                json=notification.dict()
            )
            response.raise_for_status()
            
            result = response.json()
            if result.get("status") == "success":
                notification_id = result.get("notification_id")
                logger.info(f"Created notification {notification_id}")
                return notification_id
            else:
                logger.error(f"Failed to create notification: {result}")
                raise Exception(f"Failed to create notification: {result}")
                
        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            raise
            
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose() 