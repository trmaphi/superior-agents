from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class NotificationCreate(BaseModel):
    source: str
    short_desc: str
    long_desc: str
    notification_date: str

class NotificationUpdate(BaseModel):
    id: str
    source: str
    short_desc: str
    long_desc: str
    notification_date: str

class NotificationGet(BaseModel):
    id: Optional[int] = None

class NotificationResponse(BaseModel):
    id: int
    notification_id: Optional[str] = None
    source: str
    short_desc: str
    long_desc: str
    notification_date: str
    created: str 