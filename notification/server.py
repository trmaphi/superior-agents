import uuid
from datetime import datetime
from typing import List, Optional, Dict
import os

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
from dotenv import load_dotenv

from notification_manager import AgentType, Notification, NotificationManager, NotificationPriority
from client import NotificationClient
from scrapers import TwitterScraper, CryptoNewsScraper, ScraperManager
from models import NotificationCreate, NotificationUpdate, NotificationGet, NotificationResponse

load_dotenv()

app = FastAPI(title="Notification Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

notification_manager = NotificationManager()
notification_client = NotificationClient()
scraper_manager = ScraperManager(notification_client)

# Initialize scrapers
twitter_scraper = TwitterScraper(
    api_key=os.getenv("TWITTER_API_KEY"),
    api_secret=os.getenv("TWITTER_API_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
)
crypto_news_scraper = CryptoNewsScraper()

scraper_manager.add_scraper(twitter_scraper)
scraper_manager.add_scraper(crypto_news_scraper)

# API key for authentication
API_KEY = os.getenv("API_KEY", "ccm2q324t1qv1eulq894")

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key

@app.on_event("startup")
async def startup_event():
    """Start the periodic scraping on server startup."""
    # Start periodic scraping in the background
    asyncio.create_task(scraper_manager.start_periodic_scraping())

@app.post("/api_v1/notification/create")
async def create_notification(
    notification: NotificationCreate,
    x_api_key: str = Header(...)
):
    """Create a new notification."""
    await verify_api_key(x_api_key)
    
    try:
        notification_id = notification_manager.create_notification(notification)
        return {
            "status": "success",
            "notification_id": notification_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api_v1/notification/update")
async def update_notification(
    notification: NotificationUpdate,
    x_api_key: str = Header(...)
):
    """Update an existing notification."""
    await verify_api_key(x_api_key)
    
    try:
        success = notification_manager.update_notification(notification)
        if not success:
            raise HTTPException(status_code=404, detail="Notification not found")
            
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api_v1/notification/get")
async def get_notification(
    request: NotificationGet,
    x_api_key: str = Header(...)
):
    """Get notification(s)."""
    await verify_api_key(x_api_key)
    
    try:
        # If ID is provided, get specific notification
        if request.id:
            notification = notification_manager.get_notification(request.id)
            if not notification:
                raise HTTPException(status_code=404, detail="Notification not found")
            return {"status": "success", "notification": notification}
        
        # If no ID provided, get all notifications
        notifications = notification_manager.get_all_notifications()
        return {"status": "success", "notifications": notifications}
        
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

# Scraper control endpoints
@app.post("/scrapers/run")
async def trigger_scraping():
    """Manually trigger a scraping cycle."""
    try:
        await scraper_manager.run_scraping_cycle()
        return {"status": "success", "message": "Scraping cycle completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 