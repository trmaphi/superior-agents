import json
import logging
from datetime import datetime
from typing import List, Optional

import httpx
from models import NotificationCreate, NotificationUpdate, NotificationResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://superior-crud-api.fly.dev"

class NotificationDatabaseManager:
    def __init__(self, base_url: str = BASE_URL):
        """Initialize notification database manager."""
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "x-api-key": "ccm2q324t1qv1eulq894",
            "Content-Type": "application/json"
        }
        self.client = httpx.AsyncClient(headers=self.headers, timeout=30.0)
    
    async def create_notification(self, source: str, short_desc: str, long_desc: str, notification_date: str) -> int:
        """Create a new notification."""
        url = f"{self.base_url}/api_v1/notification/create"
        
        try:
            payload = {
                "source": source,
                "short_desc": short_desc,
                "long_desc": long_desc,
                "notification_date": notification_date
            }
            
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            if result.get("status") == "success":
                notification_id = result.get("data", {}).get("notification_id")
                if notification_id:
                    logger.info(f"Created notification {notification_id}")
                    return notification_id
                raise ValueError("No notification ID in response")
            else:
                error_msg = f"Failed to create notification: {result}"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            raise
    
    async def update_notification(self, notification: NotificationUpdate) -> bool:
        """Update an existing notification."""
        url = f"{self.base_url}/api_v1/notification/update"
        
        try:
            payload = {
                "notification_id": str(notification.id),
                "source": notification.source,
                "short_desc": notification.short_desc,
                "long_desc": notification.long_desc,
                "notification_date": notification.notification_date
            }
            
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            success = result.get("status") == "success"
            if success:
                logger.info(f"Updated notification {notification.id}")
            else:
                logger.error(f"Failed to update notification: {result}")
            return success
            
        except Exception as e:
            logger.error(f"Error updating notification: {str(e)}")
            raise
    
    async def get_notification(self, notification_id: str) -> Optional[NotificationResponse]:
        """Get a specific notification."""
        url = f"{self.base_url}/api_v1/notification/get"
        
        try:
            payload = {"notification_id": str(notification_id)}
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            if result.get("status") == "success" and "notification" in result:
                notification = NotificationResponse(**result["notification"])
                logger.info(f"Retrieved notification {notification_id}")
                return notification
            else:
                logger.warning(f"Notification {notification_id} not found")
                return None
            
        except Exception as e:
            logger.error(f"Error getting notification: {str(e)}")
            raise
    
    async def get_all_notifications(self) -> List[NotificationResponse]:
        """Get all notifications."""
        url = f"{self.base_url}/api_v1/notification/get"
        
        try:
            response = await self.client.post(url, json={})
            response.raise_for_status()
            
            result = response.json()
            if result.get("status") == "success" and "data" in result:
                notifications = [NotificationResponse(**n) for n in result["data"]]
                logger.info(f"Retrieved {len(notifications)} notifications")
                return notifications
            return []
            
        except Exception as e:
            logger.error(f"Error getting all notifications: {str(e)}")
            raise
            
    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()

# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def main():
        manager = NotificationDatabaseManager()
        try:
            # Create a notification
            notification_id = await manager.create_notification(
                source="test_manager",
                short_desc="Test from manager",
                long_desc="This is a test notification from the manager",
                notification_date=datetime.utcnow().isoformat()
            )
            print(f"Created notification with ID: {notification_id}")
            
            # Get the created notification
            created = await manager.get_notification(notification_id)
            print(f"Retrieved notification: {created}")
            
            # Update the notification
            update = NotificationUpdate(
                id=notification_id,
                source="test_manager_updated",
                short_desc="Updated from manager",
                long_desc="This notification has been updated by the manager",
                notification_date=datetime.utcnow().isoformat()
            )
            success = await manager.update_notification(update)
            print(f"Update {'succeeded' if success else 'failed'}")
            
            # Get all notifications
            all_notifications = await manager.get_all_notifications()
            print(f"Total notifications: {len(all_notifications)}")
            print(all_notifications)
            
        except Exception as e:
            print(f"Error in example: {str(e)}")
        finally:
            await manager.close()
    
    asyncio.run(main()) 