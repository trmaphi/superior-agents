from typing import List
from src.genner.Base import Genner
from src.types import ChatHistory, Message


def summarize(genner: Genner, talking_points: List[str]):
	talking_points_formatted = "\n".join(talking_points)

	chat_history = ChatHistory(
		Message(role="system", content="".format(to_summarize=talking_points_formatted))
	)

	genner.ch_completion(chat_history)
