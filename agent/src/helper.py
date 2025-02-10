from contextlib import contextmanager
import os
import signal
import re
from typing import Callable, Dict, List


@contextmanager
def timeout(seconds: int):
	def timeout_handler(signum, frame):
		raise TimeoutError(f"Execution timed out after {seconds} seconds")

	# Set the timeout handler
	original_handler = signal.signal(signal.SIGALRM, timeout_handler)
	signal.alarm(seconds)

	try:
		yield
	finally:
		# Restore the original handler and cancel the alarm
		signal.alarm(0)
		signal.signal(signal.SIGALRM, original_handler)


def extract_content(text: str, block_name: str) -> str:
	"""
	Extract content between custom XML-like tags.

	Args:
		text (str): The input text containing XML-like blocks
		block_name (str): The name of the block to extract content from

	Returns:
		str: The content between the specified tags, or None if not found

	Example:
		>>> text = "<ASdasdas>\ncontent1\n</ASdasdas>\n<asdasdasdas>\ncontent2\n</asdasdasdas>"
		>>> extract_content(text, "ASdasdas")
		'content1'
	"""
	if block_name == "":
		return text

	pattern = rf"<{block_name}>\s*(.*?)\s*</{block_name}>"

	# Search for the pattern in the text
	match = re.search(pattern, text, re.DOTALL)

	# Return the content if found, None otherwise
	return match.group(1).strip() if match else ""


def services_to_prompts(services: List[str]) -> List[str]:
	service_to_prompt = {
		"Twitter": "Twitter (env vars TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_BEARER_TOKEN, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)",
		# "CoinMarketCap": "CoinMarketCap (env vars ??)",
		"CoinGecko": "CoinGecko (env vars COINGECKO_KEY)",
		"DuckDuckGo": "DuckDuckGo (command line `ddgr`)",
		"Etherscan": "Etherscan (env vars ETHERSCAN_KEY)",
		# "Arbiscan": "Arbiscan (env vars ??)",
		# "Basescan": "Basescan (env vars ??)",
		# "Alchemy": "Alchemy (env vars ??)",
		"Infura": "Infura (env vars INFURA_PROJECT_ID)",
	}

	return [service_to_prompt[service] for service in services]


def services_to_envs(platforms: List[str]) -> Dict[str, str]:
	"""
	Maps platform names to their environment variables and values.

	Args:
		platform (str): Name of the platform/service

	Returns:
		Dict[str, str]: Dictionary mapping environment variable names to their values

	Raises:
		ValueError: If platform is not supported
	"""
	env_var_mapping: Dict[str, List[str]] = {
		"Twitter": [
			"TWITTER_API_KEY",
			"TWITTER_API_SECRET",
			"TWITTER_ACCESS_TOKEN",
			"TWITTER_ACCESS_TOKEN_SECRET",
			"TWITTER_BEARER_TOKEN",
		],
		"CoinGecko": [
			"COINGECKO_KEY",
		],
		"DuckDuckGo": [],
		"Etherscan": [
			"ETHERSCAN_KEY",
		],
		"Infura": [
			"INFURA_PROJECT_ID",
		],
	}

	final_dict = {}
	for platform in platforms:
		if platform not in env_var_mapping:
			raise ValueError(
				f"Unsupported platform: {platform}. Supported platforms: {', '.join(env_var_mapping.keys())}"
			)

		# Create dictionary of environment variables and their values

		final_dict.update(
			{env_var: os.getenv(env_var, "") for env_var in env_var_mapping[platform]}
		)

	return final_dict
