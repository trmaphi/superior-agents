#!/usr/bin/env python3
import asyncio
import logging
import sys
from datetime import datetime

from dotenv import load_dotenv
from notification_database_manager import NotificationDatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def test_batch_notifications():
    """Test batch notifications functionality."""
    # Load environment variables
    load_dotenv()
    
    # Initialize notification manager
    notification_manager = NotificationDatabaseManager()
    
    try:
        # Create batch notifications
        batch_notifications = [
            {
                "source": "test_batch",
                "short_desc": f"Batch test {i}",
                "long_desc": f"This is a batch test notification {i}",
                "notification_date": datetime.utcnow().isoformat(),
                "bot_username": "test_bot"
            }
            for i in range(3)
        ]
        
        logger.info(f"Creating batch of {len(batch_notifications)} notifications")
        notification_ids = await notification_manager.create_notifications_batch(batch_notifications)
        logger.info(f"Successfully created {len(notification_ids)} notifications in batch")
        logger.info(f"Notification IDs: {notification_ids}")
        
    except Exception as e:
        logger.error(f"Error in test: {str(e)}")
    finally:
        # Close the notification manager
        await notification_manager.close()

if __name__ == "__main__":
    asyncio.run(test_batch_notifications()) 