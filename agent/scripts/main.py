from functools import partial
import json
import os
import sys
import time
from pprint import pformat
from typing import Callable, List, Tuple

import requests
import tweepy
from anthropic import Anthropic
from dotenv import load_dotenv
from duckduckgo_search import DDGS
from loguru import logger
from openai import OpenAI
from result import UnwrapError

import docker
from src.agent.marketing_2 import MarketingAgent, MarketingPromptGenerator
from src.agent.trading_2 import TradingAgent, TradingPromptGenerator
from src.container import ContainerManager
from src.datatypes import StrategyData
from src.db import APIDB
from src.db.marketing import MarketingDB
from src.genner import get_genner
from src.helper import services_to_envs, services_to_prompts
from src.llm_functions import get_summarizer
from src.sensor.marketing import MarketingSensor
from src.sensor.trading import TradingSensor
from src.twitter import TweepyTwitterClient
from src.flows.marketing import unassisted_flow as marketing_unassisted_flow
from src.flows.trading import assisted_flow as trading_assisted_flow
from src.flows.trading import unassisted_flow as trading_unassisted_flow
from src.secret import get_secrets_from_vault
from src.constant import FE_DATA_MARKETING_DEFAULTS, FE_DATA_TRADING_DEFAULTS

load_dotenv()
get_secrets_from_vault()

# Environment Variables
TWITTER_API_KEY = os.getenv("API_KEY") or ""
TWITTER_API_SECRET = os.getenv("API_KEY_SECRET") or ""
TWITTER_BEARER_TOKEN = os.getenv("BEARER_TOKEN") or ""
TWITTER_ACCESS_TOKEN = os.getenv("ACCESS_TOKEN") or ""
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET") or ""
COINGECKO_KEY = os.getenv("COINGECKO_KEY") or ""
INFURA_PROJECT_ID = os.getenv("INFURA_PROJECT_ID") or ""
ETHERSCAN_KEY = os.getenv("ETHERSCAN_KEY") or ""
ETHER_ADDRESS = os.getenv("ETHER_ADDRESS") or ""
ETHER_PRIVATE_KEY = os.getenv("ETHER_PRIVATE_KEY") or ""
DEEPSEEK_OPENROUTER_KEY = os.getenv("DEEPSEEK_OPENROUTER_KEY") or ""
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY") or ""
DEEPSEEK_KEY_2 = os.getenv("DEEPSEEK_KEY_2") or ""
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or ""

# Clients Setup
deepseek_client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=DEEPSEEK_KEY)
deepseek_2_client = Anthropic(api_key=DEEPSEEK_KEY_2)
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

HARDCODED_BASE_URL = "http://34.87.43.255:4999"


def fetch_fe_data(session_id: str):
	fe_data = FE_DATA_TRADING_DEFAULTS.copy()

	try:
		url = f"{HARDCODED_BASE_URL}/sessions/{session_id}/logs"
		response = requests.get(
			url, headers={"Accept": "text/event-stream"}, stream=True
		)
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
								payload = json.loads(
									json.dumps(first_log["payload"], indent=2)
								)
								# Update FE data
								if "model" in payload:
									fe_data["model"] = payload["model"]
								if "research_tools" in payload:
									fe_data["research_tools"] = payload[
										"research_tools"
									]
								if "trading_instruments" in payload:
									fe_data["trading_instruments"] = payload[
										"trading_instruments"
									]
								if "prompts" in payload:
									prompt_dict = {
										item["name"]: item["prompt"]
										for item in payload["prompts"]
										if isinstance(item, dict) and "name" in item
									}
									fe_data["prompts"].update(prompt_dict)
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

	logger.info(f"Final prompts: \n{pformat(fe_data["prompts"], 1)}")

	return fe_data


def setup_trading_agent_flow(
	fe_data: dict, session_id: str, assisted=True
) -> Tuple[TradingAgent, Callable[[StrategyData | None], None]]:
	agent_id = fe_data["agent_id"]
	role = fe_data["role"]
	services_used = fe_data["research_tools"]
	trading_instruments = fe_data["trading_instruments"]
	metric_name = fe_data["metric_name"]
	time_ = fe_data["time"]

	in_con_env = services_to_envs(services_used)
	apis = services_to_prompts(services_used)
	db = APIDB(base_url="https://superior-crud-api.fly.dev/api_v1")

	genner = get_genner(
		fe_data["model"],
		deepseek_client=deepseek_client,
		anthropic_client=anthropic_client,
		deepseek_2_client=deepseek_2_client,
	)
	prompt_generator = TradingPromptGenerator(prompts=fe_data["prompts"])
	sensor = TradingSensor(
		eth_address=ETHER_ADDRESS,
		infura_project_id=INFURA_PROJECT_ID,
		etherscan_api_key=ETHERSCAN_KEY,
	)
	container_manager = ContainerManager(
		docker.from_env(),
		"twitter_agent_executor",
		"./code",
		in_con_env=in_con_env,
	)
	summarizer = get_summarizer(genner)

	agent = TradingAgent(
		id=agent_id,
		sensor=sensor,
		genner=genner,
		container_manager=container_manager,
		prompt_generator=prompt_generator,
		db=db,
	)

	if assisted:
		flow_func = partial(
			trading_assisted_flow,
			agent=agent,
			session_id=session_id,
			role=role,
			time=time_,
			apis=apis,
			trading_instruments=trading_instruments,
			metric_name=metric_name,
			summarizer=summarizer,
		)
	else:
		flow_func = partial(
			trading_unassisted_flow,
			agent=agent,
			session_id=session_id,
			role=role,
			time=time_,
			apis=apis,
			trading_instruments=trading_instruments,
			metric_name=metric_name,
			summarizer=summarizer,
		)

	def wrapped_flow(prev_strat):
		return flow_func(agent=agent, prev_strat=prev_strat)

	return agent, wrapped_flow


def setup_marketing_agent_flow(
	fe_data: dict, session_id: str
) -> Tuple[MarketingAgent, Callable[[StrategyData | None], None]]:
	agent_id = fe_data["agent_id"]
	role = fe_data["role"]
	time_ = fe_data["time"]
	metric_name = fe_data["metric_name"]
	services_used = fe_data["research_tools"]

	in_con_env = services_to_envs(services_used)
	apis = services_to_prompts(services_used)
	db = APIDB(base_url="https://superior-crud-api.fly.dev/api_v1")

	auth = tweepy.OAuth1UserHandler(
		consumer_key=TWITTER_API_KEY,
		consumer_secret=TWITTER_API_SECRET,
	)
	auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)

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
	sensor = MarketingSensor(twitter_client, DDGS())
	genner = get_genner(
		fe_data["model"],
		deepseek_client=deepseek_client,
		anthropic_client=anthropic_client,
		deepseek_2_client=deepseek_2_client,
	)
	container_manager = ContainerManager(
		docker.from_env(),
		"twitter_agent_executor",
		"./code",
		in_con_env=in_con_env,
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

	summarizer = get_summarizer(genner)

	flow_func = partial(
		marketing_unassisted_flow,
		agent=agent,
		session_id=session_id,
		role=role,
		time=time_,
		apis=apis,
		metric_name=metric_name,
		summarizer=summarizer,
	)

	def wrapped_flow(prev_strat):
		return flow_func(agent=agent, prev_strat=prev_strat)

	return agent, wrapped_flow


if __name__ == "__main__":
	if len(sys.argv) < 3:
		print("Usage: python main.py [trading|marketing] [session_id]")
		agent_type = "trading"
		session_id = "test"
	else:
		agent_type = sys.argv[1]
		session_id = sys.argv[2]

	fe_data = fetch_fe_data(session_id)
	logger.info(f"Running {agent_type} agent for session {session_id}")

	if agent_type == "trading":
		agent, flow = setup_trading_agent_flow(fe_data, session_id)

		while True:
			prev_strat = agent.db.fetch_latest_strategy(agent.id)
			flow(prev_strat)
			logger.info("Waiting for 15 seconds...")
			time.sleep(15)

	elif agent_type == "marketing":
		agent, flow = setup_marketing_agent_flow(fe_data, session_id)

		while True:
			prev_strat = agent.db.fetch_latest_strategy(agent.id)
			flow(prev_strat)
			logger.info("Waiting for 15 seconds...")
			time.sleep(15)
	else:
		logger.error(f"Unknown agent type: {agent_type}")
		sys.exit(1)
