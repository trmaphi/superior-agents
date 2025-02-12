from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class NotificationCreate(BaseModel):
    source: str
    short_desc: str
    long_desc: str
    notification_date: str

class NotificationUpdate(BaseModel):
    id: int
    source: str
    short_desc: str
    long_desc: str
    notification_date: str

class NotificationGet(BaseModel):
    id: Optional[int] = None

class NotificationResponse(BaseModel):
    id: int
    source: str
    short_desc: str
    long_desc: str
    notification_date: str
    inserted_at: str 