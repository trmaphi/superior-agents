from abc import ABC
from typing import Dict, NamedTuple


class OllamaConfig(ABC):
    name: str
    endpoint: str = "http://localhost:11434/api/chat"
    model: str
    stream: bool


class DeepseekConfig(OllamaConfig):
    name: str = "Ollama DeepSeek"
    model: str = "deepseek-coder:6.7b"
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False


class QwenConfig(OllamaConfig):
    name: str = "Ollama Qwen"
    model: str = "qwen2.5-coder:latest"

    stream: bool = False
