import json
import os
import sys
from typing import Callable, List

import requests
import tweepy
from anthropic import Anthropic
from anthropic import Anthropic as DeepSeekClient
from dotenv import load_dotenv
from duckduckgo_search import DDGS
from loguru import logger
from openai import OpenAI as DeepSeek
from result import UnwrapError

import docker
from src.agent.marketing import MarketingAgent, MarketingPromptGenerator
from src.container import ContainerManager
from src.datatypes import StrategyData, StrategyInsertData
from src.db import APIDB
from src.flows.marketing import unassisted_flow
from src.genner import get_genner
from src.helper import services_to_envs, services_to_prompts
from src.summarizer import get_summarizer
from src.secret import get_secrets_from_vault
from src.sensor.marketing import MarketingSensor
from src.twitter import TweepyTwitterClient

get_secrets_from_vault()
load_dotenv()

STARTER_STR = os.getenv("STARTER_STR") or "Starting!!!"
ENDING_STR = os.getenv("ENDING_STR") or "Ending!!!"

TWITTER_API_KEY = os.getenv("API_KEY") or ""
TWITTER_API_SECRET = os.getenv("API_KEY_SECRET") or ""
TWITTER_ACCESS_TOKEN = os.getenv("BEARER_TOKEN") or ""
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN") or ""
TWITTER_BEARER_TOKEN = os.getenv("ACCESS_TOKEN_SECRET") or ""

os.environ["TWITTER_API_KEY"] = TWITTER_API_KEY
os.environ["TWITTER_API_SECRET"] = TWITTER_API_SECRET
os.environ["TWITTER_ACCESS_TOKEN"] = TWITTER_ACCESS_TOKEN
os.environ["TWITTER_ACCESS_TOKEN_SECRET"] = TWITTER_ACCESS_TOKEN_SECRET
os.environ["TWITTER_BEARER_TOKEN"] = TWITTER_BEARER_TOKEN

COINGECKO_KEY = os.getenv("COINGECKO_KEY") or ""
INFURA_PROJECT_ID = os.getenv("INFURA_PROJECT_ID") or ""
ETHERSCAN_KEY = os.getenv("ETHERSCAN_KEY") or ""

DEEPSEEK_OPENROUTER_KEY = os.getenv("DEEPSEEK_OPENROUTER_KEY") or ""
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY") or ""
DEEPSEEK_KEY_2 = os.getenv("DEEPSEEK_KEY_2") or ""
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or ""


if __name__ == "__main__":
	logger.info(STARTER_STR)

	deepseek_client = DeepSeek(
		base_url="https://openrouter.ai/api/v1", api_key=DEEPSEEK_KEY
	)
	deepseek_2_client = DeepSeekClient(api_key=DEEPSEEK_KEY_2)
	anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

	HARDCODED_BASE_URL = "http://34.87.43.255:4999"

	# Collect args[1] as session id
	session_id = sys.argv[1]

	logger.info(f"Session ID: {session_id}")

	# Connect to SSE endpoint to get session logs
	url = f"{HARDCODED_BASE_URL}/sessions/{session_id}/logs"
	headers = {"Accept": "text/event-stream"}
	logger.info("Marketing start")

	# Initialize fe_data with default values
	fe_data = {
		"model": "deepseek_2",
		"agent_id": "testing_marketing_agent",
		"metric_name": "follower_count",
		"research_tools": [
			"Twitter",
			"DuckDuckGo",
			"CoinGecko",
			"Etherscan",
			"Infura",
		],
		"prompts": {},  # Will be filled with default prompts if none provided
	}

	try:
		response = requests.get(url, headers=headers, stream=True)

		for line in response.iter_lines():
			if line:
				decoded_line = line.decode("utf-8")
				if decoded_line.startswith("data: "):
					data = json.loads(decoded_line[6:])
					if "logs" in data:
						log_entries = data["logs"].strip().split("\n")
						if log_entries:
							first_log = json.loads(log_entries[0])
							if first_log["type"] == "request":
								logger.info("Processing initial prompt payload")

								payload = json.loads(
									json.dumps(first_log["payload"], indent=2)
								)

								# Update non-prompt fields
								if "model" in payload:
									fe_data["model"] = payload["model"]

								if "research_tools" in payload and isinstance(
									payload["research_tools"], list
								):
									fe_data["research_tools"] = payload[
										"research_tools"
									]

								# Handle custom prompts
								if "prompts" in payload and isinstance(
									payload["prompts"], list
								):
									# Convert list of prompt dicts to name:prompt dictionary
									received_prompts = {
										item["name"]: item["prompt"]
										for item in payload["prompts"]
										if isinstance(item, dict)
										and "name" in item
										and "prompt" in item
									}
									fe_data["prompts"].update(received_prompts)

								logger.info("Received frontend data with prompts:")
								logger.info(
									f"Received prompts: {list(fe_data['prompts'].keys())}"
								)
								break

		# Get default prompts
		default_prompts = MarketingPromptGenerator.get_default_prompts()
		logger.info(f"Available default prompts: {list(default_prompts.keys())}")

		# Only fill in missing prompts from defaults
		missing_prompts = set(default_prompts.keys()) - set(fe_data["prompts"].keys())
		if missing_prompts:
			logger.info(f"Adding missing default prompts: {list(missing_prompts)}")
			for key in missing_prompts:
				fe_data["prompts"][key] = default_prompts[key]
	except Exception as e:
		logger.error(f"Error fetching session logs: {e}, going with defaults")
		# In case of error, return fe_data with default prompts
		default_prompts = MarketingPromptGenerator.get_default_prompts()
		fe_data["prompts"].update(default_prompts)

	logger.info(f"Final prompts: {fe_data["prompts"]}")

	agent_id = fe_data["agent_id"]
	role = fe_data["role"]
	time = fe_data["time"]
	metric_name = fe_data["metric_name"]
	services_used = fe_data["research_tools"]

	model_name = "deepseek_2"
	in_con_env = services_to_envs(services_used)
	apis = services_to_prompts(services_used)

	auth = tweepy.OAuth1UserHandler(
		consumer_key=TWITTER_API_KEY,
		consumer_secret=TWITTER_API_SECRET,
	)
	auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)

	ddgs = DDGS()
	db = APIDB()
	twitter_client = TweepyTwitterClient(
		client=tweepy.Client(
			bearer_token=TWITTER_BEARER_TOKEN,
			consumer_key=TWITTER_API_KEY,
			consumer_secret=TWITTER_API_SECRET,
			access_token=TWITTER_ACCESS_TOKEN,
			access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
		),
		api_client=tweepy.API(auth),
	)
	sensor = MarketingSensor(twitter_client, ddgs)

	genner = get_genner(
		model_name,
		deepseek_client=deepseek_client,
		anthropic_client=anthropic_client,
		deepseek_2_client=deepseek_2_client,
	)
	docker_client = docker.from_env()
	container_manager = ContainerManager(
		docker_client, "twitter_agent_executor", "./code", in_con_env=in_con_env
	)
	prompt_generator = MarketingPromptGenerator(fe_data["prompts"])

	agent = MarketingAgent(
		id=agent_id,
		db=db,
		sensor=sensor,
		genner=genner,
		container_manager=container_manager,
		prompt_generator=prompt_generator,
	)

	prev_strat = db.fetch_latest_strategy(agent_id)
	summarizer = get_summarizer(genner)

	unassisted_flow(
		agent=agent,
		session_id=session_id,
		role=role,
		time=time,
		apis=apis,
		metric_name=metric_name,
		prev_strat=prev_strat,
		summarizer=summarizer,
	)

	logger.info(ENDING_STR)
