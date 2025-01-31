from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uvicorn

from src.types import Message
from src.db import SqliteDB

app = FastAPI()
db = SqliteDB()


# Pydantic models for request/response validation
class MessageModel(BaseModel):
	role: str
	content: str
	metadata: str


@app.get("/chat_history")
async def get_messages() -> List[MessageModel]:
	try:
		messages = db.get_all_chat_history()
		# Convert Pydantic model to your domain model
		messages = [
			MessageModel(role=msg.role, content=msg.content, metadata=str(msg.metadata))
			for msg in messages
		]

		return messages
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
	uvicorn.run(app, host="0.0.0.0", port=8000)
