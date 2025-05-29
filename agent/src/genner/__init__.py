from typing import Callable

from anthropic import Anthropic
from openai import OpenAI

from src.client.openrouter import OpenRouter
from src.config import (
	ClaudeConfig,
	DeepseekConfig,
	OAIConfig,
	OllamaConfig,
	OpenRouterConfig,
)
from src.genner.Claude import ClaudeGenner
from src.genner.OAI import OAIGenner
from src.genner.OR import OpenRouterGenner

from .Base import Genner
from .Deepseek import DeepseekGenner
from .Qwen import QwenGenner
from tests.mock_genner.MockGenner import MockGenner

__all__ = ["get_genner", "QwenGenner", "OllamaConfig"]


class BackendException(Exception):
	pass


class DeepseekBackendException(Exception):
	pass


class ClaudeBackendException(Exception):
	pass


available_backends = [
	"deepseek",
	"deepseek_or",
	"deepseek_v3",
	"deepseek_v3_or",
	"openai",
	"gemini",
	"claude",
	"qwq",
]


def get_genner(
	backend: str,
	stream_fn: Callable[[str], None] | None,
	deepseek_deepseek_client: OpenAI | None = None,
	deepseek_local_client: OpenAI | None = None,
	anthropic_client: Anthropic | None = None,
	or_client: OpenRouter | None = None,
	llama_client: OpenAI | None = None,
	deepseek_config: DeepseekConfig = DeepseekConfig(),
	claude_config: ClaudeConfig = ClaudeConfig(),
	openai_config: OpenRouterConfig = OpenRouterConfig(),
	gemini_config: OpenRouterConfig = OpenRouterConfig(),
	llama_config: OAIConfig = OAIConfig(),
	qwq_config: OpenRouterConfig = OpenRouterConfig(),
) -> Genner:
	"""
	Get a genner instance based on the backend.

	Args:
		backend (str): The backend to use.
		deepseek_deepseek_client (OpenAI): OpenAI client but endpoint are pointed towards deepseek endpoint for deepseek-r1.
		deepseek_or_client (OpenAI): OpenAI client but endpoint are pointed towards openrouter endpoint for deepseek-r1.
		deepseek_local_client (OpenAI): OpenAI client but endpoint are pointed towards local endpoint for deepseek-r1.
		deepseek_config (DeepseekConfig, optional): The configuration for the Deepseek backend. Defaults to DeepseekConfig().
		qwen_config (QwenConfig, optional): The configuration for the Qwen backend. Defaults to QwenConfig().

	Raises:
		BackendException: If the backend is not supported.
		OaiBackendException: If the OpenAI client is required for the OAI backend but not provided.
		ClaudeBackendException: If the Anthropic client is required for the Claude backend but not provided.

	Returns:
		Genner: The genner instance.
	"""

	if backend == "deepseek":
		deepseek_config.model = "deepseek-reasoner"
		if not deepseek_deepseek_client:
			raise DeepseekBackendException(
				"Using backend 'deepseek', DeepSeek (openai) client is not provided."
			)

		return DeepseekGenner(deepseek_deepseek_client, deepseek_config, stream_fn)
	elif backend == "deepseek_or":
		deepseek_config.model = "deepseek/deepseek-r1"
		deepseek_config.max_tokens = 32768
		if not or_client:
			raise DeepseekBackendException(
				"Using backend 'deepseek_or', OpenRouter client is not provided."
			)

		return DeepseekGenner(or_client, deepseek_config, stream_fn)
	elif backend == "deepseek_v3":
		deepseek_config.model = "deepseek/deepseek-chat"
		deepseek_config.max_tokens = 32768

		if not or_client:
			raise DeepseekBackendException(
				"Using backend 'deepseek_v3', OpenRouter client is not provided."
			)

		return DeepseekGenner(or_client, deepseek_config, stream_fn)
	elif backend == "local":
		deepseek_config.model = "../DeepSeek-R1-Q4_K_M/DeepSeek-R1-Q4_K_M/DeepSeek-R1-Q4_K_M-00001-of-00011.gguf"
		deepseek_config.model = "../DeepSeek-R1-Q4_K_M/DeepSeek-R1-Q4_K_M/DeepSeek-R1-Q4_K_M-00001-of-00011.gguf"

		if not deepseek_local_client:
			raise DeepseekBackendException(
				"Using backend 'deepseek', DeepSeek Local (openai) client is not provided."
			)

		return DeepseekGenner(deepseek_local_client, deepseek_config, stream_fn)
	elif backend == "claude":
		if not anthropic_client:
			raise ClaudeBackendException(
				"Using backend 'claude', Anthropic client is not provided."
			)

		return ClaudeGenner(anthropic_client, claude_config, stream_fn)
	elif backend == "openai":
		openai_config.name = "o3-mini"
		openai_config.model = "o3-mini"

		if not or_client:
			return OAIGenner(
				client=OpenAI(), 
				config=OAIConfig(name=openai_config.name, model=openai_config.model), 
				stream_fn=stream_fn
			)

		return OpenRouterGenner(or_client, openai_config, stream_fn)
	elif backend == "deepseek_v3_or":
		deepseek_config.model = "deepseek/deepseek-chat"
		deepseek_config.max_tokens = 32768
		deepseek_config.temperature = 0

		if not or_client:
			raise DeepseekBackendException(
				"Using backend 'deepseek_v3_or', OpenRouter client is not provided."
			)

		return DeepseekGenner(or_client, deepseek_config, stream_fn)
	elif backend == "gemini":
		gemini_config.name = "google/gemini-2.0-flash-lite-001"
		gemini_config.model = "google/gemini-2.0-flash-lite-001"

		if not or_client:
			raise Exception(
				"Using backend 'gemini', OpenRouter client is not provided."
			)

		return OpenRouterGenner(or_client, gemini_config, stream_fn)
	elif backend == "llama":
		llama_config.name = "NousResearch/Meta-Llama-3-8B"
		llama_config.model = "NousResearch/Meta-Llama-3-8B"

		if not llama_client:
			raise Exception("Using backend 'llama', Llama client is not provided.")

		return OAIGenner(llama_client, llama_config, stream_fn)
	elif backend == "qwq":
		qwq_config.name = "qwen/qwq-32b"
		qwq_config.model = "qwen/qwq-32b"

		if not or_client:
			raise Exception("Using backend 'qwq', OpenRouter client is not provided.")

		return OpenRouterGenner(or_client, qwq_config, stream_fn)
	elif backend == "mock":
		return MockGenner()
	raise BackendException(
		f"Unsupported backend: {backend}, available backends: {', '.join(available_backends)}"
	)
