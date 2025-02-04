from anthropic import Anthropic
from openai import OpenAI
from src.config import (
	ClaudeConfig,
	DeepseekConfig,
	QwenConfig,
)
from src.genner.Claude import ClaudeGenner
from .Base import Genner
from .Deepseek import DeepseekGenner
from .Qwen import QwenGenner

__all__ = ["get_genner"]


class BackendException(Exception):
	pass


class DeepseekBackendException(Exception):
	pass


class ClaudeBackendException(Exception):
	pass


available_backends = ["deepseek", "qwen"]


def get_genner(
	backend: str,
	deepseek_client: OpenAI | None = None,
	deepseek_config: DeepseekConfig = DeepseekConfig(),
	deepseek_2_client: Anthropic | None = None,
	claude_client: Anthropic | None = None,
	claude_config: ClaudeConfig = ClaudeConfig(),
	qwen_config: QwenConfig = QwenConfig(),
) -> Genner:
	"""
	Get a genner instance based on the backend.

	Args:
		backend (str): The backend to use.
		deepseek_client (OpenAI): OpenAI client but endpoint are pointed towards deepseek endpoints.
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
		if not deepseek_client:
			raise DeepseekBackendException(
				"Using backend 'deepseek', OpenAI client is not provided."
			)

		return DeepseekGenner(deepseek_client, deepseek_config)
	elif backend == "deepseek_2":
		if not deepseek_2_client:
			raise DeepseekBackendException(
				"Using backend 'deepseek_2', OpenAI client is not provided."
			)

		return ClaudeGenner(deepseek_2_client, claude_config)
	elif backend == "claude":
		if not claude_client:
			raise DeepseekBackendException(
				"Using backend 'claude', OpenAI client is not provided."
			)

		return ClaudeGenner(claude_client, claude_config)
	elif backend == "qwen":
		return QwenGenner(qwen_config)
	elif backend == "qwen-uncensored":
		qwen_config.model = "qwen-uncensored:latest"
		return QwenGenner(qwen_config)
	elif backend == "deepseek":
		if not deepseek_client:
			raise DeepseekBackendException(
				"Using backend 'oai', OpenAI client is required for OAI backend"
			)
		return DeepseekGenner(deepseek_client, deepseek_config)

	raise BackendException(
		f"Unsupported backend: {backend}, available backends: {', '.join(available_backends)}"
	)
