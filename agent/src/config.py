from abc import ABC
from typing import Dict, NamedTuple
from dataclasses import dataclass


@dataclass
class BaseLLMConfig(ABC):
	pass


@dataclass
class OllamaConfig(BaseLLMConfig):
	name: str | None = None
	model: str | None = None
	endpoint: str = "http://localhost:11434/api/chat"


@dataclass
class DeepseekConfig(BaseLLMConfig):
	name: str = "Deepseek"
	# model: str = "deepseek-chat"
	# model = "./DeepSeek-R1-Q4_K_M/DeepSeek-R1-Q4_K_M/DeepSeek-R1-Q4_K_M-00001-of-00011.gguf"
	model: str = "deepseek/deepseek-r1"
	max_tokens: int = 8192


@dataclass
class QwenConfig(BaseLLMConfig):
	name: str = "Ollama Qwen"
	model: str = "qwen2.5-coder:latest"


@dataclass
class ClaudeConfig(BaseLLMConfig):
	name: str = "Claude"
	model: str = "claude-3-5-sonnet-latest"
	max_tokens = 4096
