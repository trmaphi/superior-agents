import json
import logging
from datetime import datetime
from typing import List, Optional

import requests
from models import NotificationCreate, NotificationUpdate, NotificationResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://superior-crud-api.fly.dev"

class NotificationManager:
    def __init__(self, base_url: str = BASE_URL):
        """Initialize notification manager."""
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json"
        }
    
    def create_notification(self, notification: NotificationCreate) -> int:
        """Create a new notification."""
        url = f"{self.base_url}/api_v1/notification/create"
        
        try:
            payload = json.dumps({
                "source": notification.source,
                "short_desc": notification.short_desc,
                "long_desc": notification.long_desc,
                "notification_date": notification.notification_date
            })
            
            response = requests.post(url, headers=self.headers, data=payload)
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
    
    def update_notification(self, notification: NotificationUpdate) -> bool:
        """Update an existing notification."""
        url = f"{self.base_url}/api_v1/notification/update"
        
        try:
            payload = json.dumps({
                "id": str(notification.id),  # Convert to string as expected by API
                "source": notification.source,
                "short_desc": notification.short_desc,
                "long_desc": notification.long_desc,
                "notification_date": notification.notification_date
            })
            
            response = requests.post(url, headers=self.headers, data=payload)
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
    
    def get_notification(self, notification_id: int) -> Optional[NotificationResponse]:
        """Get a specific notification."""
        url = f"{self.base_url}/api_v1/notification/get"
        
        try:
            payload = json.dumps({"id": str(notification_id)})
            response = requests.post(url, headers=self.headers, data=payload)
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
    
    def get_all_notifications(self) -> List[NotificationResponse]:
        """Get all notifications."""
        url = f"{self.base_url}/api_v1/notification/get"
        
        try:
            payload = json.dumps({})  # Empty payload to get all notifications
            response = requests.post(url, headers=self.headers, data=payload)
            response.raise_for_status()
            
            result = response.json()
            if result.get("status") == "success" and "notifications" in result:
                notifications = [NotificationResponse(**n) for n in result["notifications"]]
                logger.info(f"Retrieved {len(notifications)} notifications")
                return notifications
            return []
            
        except Exception as e:
            logger.error(f"Error getting all notifications: {str(e)}")
            raise

# Example usage
if __name__ == "__main__":
    manager = NotificationManager()
    
    try:
        # Create a notification
        notification = NotificationCreate(
            source="test_manager",
            short_desc="Test from manager",
            long_desc="This is a test notification from the manager",
            notification_date="2024-01-01 00:00:00"
        )
        notification_id = manager.create_notification(notification)
        print(f"Created notification with ID: {notification_id}")
        
        # Get the created notification
        created = manager.get_notification(notification_id)
        print(f"Retrieved notification: {created}")
        
        # Update the notification
        update = NotificationUpdate(
            id=notification_id,
            source="test_manager_updated",
            short_desc="Updated from manager",
            long_desc="This notification has been updated by the manager",
            notification_date="2024-01-01 00:00:00"
        )
        success = manager.update_notification(update)
        print(f"Update {'succeeded' if success else 'failed'}")
        
        # Get all notifications
        all_notifications = manager.get_all_notifications()
        print(f"Total notifications: {len(all_notifications)}")
        
    except Exception as e:
        print(f"Error in example: {str(e)}") 