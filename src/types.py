from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, List, Dict, Optional, Tuple, TypeAlias
from enum import Enum, auto


class Message:
	def __init__(self, role: str, content: str, metadata: Dict[str, Any] = {}):
		self.role = role
		self.content = content
		self.metadata: Dict[str, Any] = metadata

	def as_native(self) -> Dict[str, str]:
		return {"role": self.role, "content": self.content}

	@staticmethod
	def from_native(native: Dict[str, Any]) -> "Message":
		assert "role" in native
		assert "content" in native

		return Message(
			role=native["role"],
			content=native["content"],
			metadata=native.get("metadata", {}),
		)

	def __repr__(self) -> str:
		return (
			"Message("
			f"\n\trole={self.role}, "
			f"\n\tcontent={self.content[:10]}..."
			f"\n\tmetadata={self.metadata}"
			"\n)"
		)


# Example :
# convo = [
#   {"role": "system": "content": "..."},
#   {"role": "user": "content": "..."},
#   {"role": "assistant": "content": "..."},
#   {"role": "user": "content": "..."},
#   {"role": "assistant": "content": "..."},
# ]


class ChatHistory:
	def __init__(self, messages: List[Message] | Message = []):
		self.messages: List[Message] = (
			messages if isinstance(messages, list) else [messages]
		)

	def __len__(self) -> int:
		return len(self.messages)

	def __add__(self, other: "ChatHistory") -> "ChatHistory":
		return ChatHistory(messages=self.messages + other.messages)

	def as_native(self) -> List[Dict[str, str]]:
		return [message.as_native() for message in self.messages]

	@staticmethod
	def from_native(native: List[Dict[str, str]]) -> "ChatHistory":
		return ChatHistory(
			messages=[Message.from_native(message) for message in native]
		)

	def __repr__(self) -> str:
		messages_repr = "\n".join([message.__repr__() for message in self.messages])
		return "PList(" f"\n\tmessages=[\n\t\t" f"{messages_repr}" "\n\t\t]" "\n)"

	def modify_message_at_index(
		self, index: int, new_message: Message
	) -> "ChatHistory":
		self.messages[index] = new_message

		return self

	def modify_message_metadata_at_index(
		self, index: int, new_metadata: Dict[str, str]
	) -> "ChatHistory":
		self.messages[index].metadata = new_metadata

		return self

	def get_x_metadata(self, x: str) -> List[str]:
		return [message.metadata[x] for message in self.messages]

