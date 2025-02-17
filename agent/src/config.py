from abc import ABC
from typing import Dict, NamedTuple


class OllamaConfig(ABC):
    name: str
    endpoint: str = "http://localhost:11434/api/chat"
    model: str
    stream: bool


class DeepseekConfig(OllamaConfig):
    name = "Deepseek R1"
    # model: str = "deepseek-chat"
    # model = "./DeepSeek-R1-Q4_K_M/DeepSeek-R1-Q4_K_M/DeepSeek-R1-Q4_K_M-00001-of-00011.gguf"
    model = "deepseek/deepseek-r1"
    max_tokens=16000
    stream: bool = False


class QwenConfig(OllamaConfig):
    name: str = "Ollama Qwen"
    model: str = "qwen2.5-coder:latest"

    stream: bool = False

class ClaudeConfig():
    name: str = "Claude"
    model: str = "claude-3-5-sonnet-latest"
    max_tokens = 4096
    