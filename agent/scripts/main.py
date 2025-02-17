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
from src.agent.marketing import MarketingAgent, MarketingPromptGenerator
from src.agent.trading import TradingAgent, TradingPromptGenerator
from src.container import ContainerManager
from src.datatypes import StrategyData
from src.db import APIDB
from src.genner import get_genner
from src.helper import services_to_envs, services_to_prompts
from src.summarizer import get_summarizer
from src.sensor.marketing import MarketingSensor
from src.sensor.trading import TradingSensor
from src.twitter import TweepyTwitterClient
from src.flows.marketing import unassisted_flow as marketing_unassisted_flow
from src.flows.trading import assisted_flow as trading_assisted_flow
from src.flows.trading import unassisted_flow as trading_unassisted_flow
from src.rag import StrategyRAG

import uuid

load_dotenv()

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
DEEPSEEK_OPENROUTER_API_KEY = os.getenv("DEEPSEEK_OPENROUTER_API_KEY") or ""
DEEPSEEK_DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_DEEPSEEK_API_KEY") or ""
DEEPSEEK_LOCAL_API_KEY = os.getenv("DEEPSEEK_LOCAL_API_KEY") or ""
DEEPSEEK_URL = os.getenv("DEEPSEEK_URL")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or ""
API_DB_BASE_URL = os.getenv('API_DB_BASE_URL') or ""
API_DB_API_KEY = os.getenv('API_DB_API_KEY') or ""
OAI_API_KEY = os.getenv("OAI_API_KEY") or ""

# Clients Setup
deepseek_or_client = OpenAI(
	base_url="https://openrouter.ai/api/v1", api_key=DEEPSEEK_OPENROUTER_API_KEY
)
deepseek_local_client = OpenAI(base_url=DEEPSEEK_URL, api_key=DEEPSEEK_LOCAL_API_KEY)
deepseek_deepseek_client = OpenAI(
	base_url="https://api.deepseek.com", api_key=DEEPSEEK_DEEPSEEK_API_KEY
)
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
oai_client = OpenAI(api_key=OAI_API_KEY)



def fetch_input(type: str):
	payload = {}
	if type == 'trading':
		with open('starter/trading.json','r') as f:
			payload = json.loads(f.read())
	elif type == 'marketing':
		with open('starter/marketing.json','r') as f:
			payload = json.loads(f.read())
	
	return payload


def setup_trading_agent_flow(
	payload_input: dict, session_id: str, assisted=True
) -> Tuple[TradingAgent, List[str], Callable[[StrategyData | None, str | None], None]]:
	agent_id = payload_input["agent_id"]
	role = payload_input["role"]
	services_used = payload_input["research_tools"]
	trading_instruments = payload_input["trading_instruments"]
	metric_name = payload_input["metric_name"]
	notif_sources = payload_input["notifications"]
	time_ = payload_input["time"]

	in_con_env = services_to_envs(services_used)
	apis = services_to_prompts(services_used)
	db = APIDB(base_url=API_DB_BASE_URL, api_key=API_DB_API_KEY)

	genner = get_genner(
		payload_input["model"],
		deepseek_deepseek_client=deepseek_deepseek_client,
		deepseek_or_client=deepseek_or_client,
		deepseek_local_client=deepseek_local_client,
		anthropic_client=anthropic_client,
	)
	prompt_generator = TradingPromptGenerator(prompts=payload_input["prompts"])
	sensor = TradingSensor(
		eth_address=ETHER_ADDRESS,
		infura_project_id=INFURA_PROJECT_ID,
		etherscan_api_key=ETHERSCAN_KEY,
	)
	container_manager = ContainerManager(
		docker.from_env(),
		f"docker-agent-executor",
		"./code",
		in_con_env=in_con_env,
	)
	summarizer = get_summarizer(genner)
	previous_strategies = db.fetch_all_strategies(agent_id)

	rag = StrategyRAG(
		agent_id=agent_id,
		oai_client=oai_client,
		strategies=previous_strategies,
		storage_dir="./rag/trading",
	)

	agent = TradingAgent(
		id=agent_id,
		rag=rag,
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

	def wrapped_flow(prev_strat, notif_str):
		return flow_func(agent=agent, prev_strat=prev_strat, notif_str=notif_str)

	return agent, notif_sources, wrapped_flow


def setup_marketing_agent_flow(
	payload_input: dict, session_id: str
) -> Tuple[
	MarketingAgent, List[str], Callable[[StrategyData | None, str | None], None]
]:
	agent_id = payload_input["agent_id"]
	role = payload_input["role"]
	time_ = payload_input["time"]
	metric_name = payload_input["metric_name"]
	notif_sources = payload_input["notifications"]
	services_used = payload_input["research_tools"]

	in_con_env = services_to_envs(services_used)
	apis = services_to_prompts(services_used)
	db = APIDB(base_url=API_DB_BASE_URL, api_key=API_DB_API_KEY)

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
		payload_input["model"],
		deepseek_deepseek_client=deepseek_deepseek_client,
		deepseek_or_client=deepseek_or_client,
		deepseek_local_client=deepseek_local_client,
		anthropic_client=anthropic_client,
	)
	container_manager = ContainerManager(
		docker.from_env(),
		f"docker-agent-executor",
		"./code",
		in_con_env=in_con_env,
	)
	prompt_generator = MarketingPromptGenerator(payload_input["prompts"])

	previous_strategies = db.fetch_all_strategies(agent_id)
	rag = StrategyRAG(
		agent_id=agent_id,
		oai_client=oai_client,
		strategies=previous_strategies,
		storage_dir="./rag/trading",
	)

	agent = MarketingAgent(
		id=agent_id,
		db=db,
		rag=rag,
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

	def wrapped_flow(prev_strat, notif_str):
		return flow_func(agent=agent, prev_strat=prev_strat, notif_str=notif_str)

	return agent, notif_sources, wrapped_flow


if __name__ == "__main__":
	if len(sys.argv) < 3:
		print("Usage: python main.py [trading|marketing] [agent_id]")
		agent_type = "trading"
		agent_id = "agent_001"
	else:
		agent_type = sys.argv[1]
		agent_id = sys.argv[2]
	
	db = APIDB(base_url=API_DB_BASE_URL, api_key=API_DB_API_KEY)
	session_id = str(uuid.uuid4())
	db.create_agent_sessions(session_id,agent_id,"running")

	payload_input = fetch_input(agent_type)
	payload_input['agent_id'] = agent_id
	db.update_agent(agent_id,configuration=json.dumps(payload_input))
	logger.info(f"Running {agent_type} agent for session {session_id}")

	if agent_type == "trading":
		agent, notif_sources, flow = setup_trading_agent_flow(payload_input, session_id)

		flow(None, None)
		logger.info("Waiting for 15 seconds...")
		time.sleep(15)

		while True:
			prev_strat = agent.db.fetch_latest_strategy(agent.id)
			current_notif = agent.db.fetch_latest_notification_str(notif_sources)
			agent.rag.add_strategy(prev_strat)
			flow(prev_strat, None)
			logger.info("Waiting for 15 seconds...")
			time.sleep(15)

	elif agent_type == "marketing":
		agent, notif_sources, flow = setup_marketing_agent_flow(payload_input, session_id)

		flow(None, None)
		logger.info("Waiting for 15 seconds...")
		time.sleep(15)

		while True:
			prev_strat = agent.db.fetch_latest_strategy(agent.id)
			current_notif = agent.db.fetch_latest_notification_str(notif_sources)
			agent.rag.add_strategy(prev_strat)
			flow(prev_strat, None)
			logger.info("Waiting for 15 seconds...")
			time.sleep(15)
	else:
		logger.error(f"Unknown agent type: {agent_type}")
		sys.exit(1)
