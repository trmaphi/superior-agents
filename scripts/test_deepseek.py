from dotenv import load_dotenv
from src.genner import get_genner
from openai import OpenAI
import os

from src.types import ChatHistory, Message

load_dotenv()

deepseek_client = OpenAI(
	base_url="https://openrouter.ai/api/v1",
    api_key="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"
)

genner = get_genner("deepseek", deepseek_client=deepseek_client)

response = genner.ch_completion(
	ChatHistory(Message(role="system", content="Hi, who are you?"))
)

print(response.unwrap())
