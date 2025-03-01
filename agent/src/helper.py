from contextlib import contextmanager
from datetime import datetime
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
		"CoinGecko": "CoinGecko (env vars COINGECKO_API_KEY) (example usage `curl -X GET 'https://api.coingecko.com/api/v3/ping' -H 'x-cg-demo-api-key: YOUR_API_KEY'` to ping coingecko",
		"DuckDuckGo": "DuckDuckGo (command line `ddgr`) (example usage `ddgr --json x` to search for x)",
		"Etherscan": "Etherscan (env vars ETHERSCAN_API_KEY)",
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
			"COINGECKO_API_KEY",
		],
		"DuckDuckGo": [],
		"Etherscan": [
			"ETHERSCAN_API_KEY",
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


def get_latest_notifications_by_source(notifications: List[Dict]) -> List[Dict]:
	"""
	Get the latest notification for each source based on the created timestamp.

	Args:
		notifications (List[Dict]): List of notification dictionaries

	Returns:
		List[Dict]: List of latest notifications, one per source
	"""
	# Group notifications by source
	source_groups: Dict[str, List[Dict]] = {}
	for notif in notifications:
		source = notif["source"]
		if source not in source_groups:
			source_groups[source] = []
		source_groups[source].append(notif)

	# Get latest notification for each source
	latest_notifications = []
	for source, notifs in source_groups.items():
		# Sort notifications by created timestamp in descending order
		sorted_notifs = sorted(
			notifs, key=lambda x: datetime.fromisoformat(x["created"]), reverse=True
		)
		# Add the first (latest) notification
		latest_notifications.append(sorted_notifs[0])

	return latest_notifications
