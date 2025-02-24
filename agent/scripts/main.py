import datetime
import json
import os
import sys
import time
from functools import partial
from typing import Callable, List, Tuple

import requests
import tweepy
from anthropic import Anthropic
from dotenv import load_dotenv
from duckduckgo_search import DDGS
from loguru import logger
from openai import OpenAI

import docker
from src.agent.marketing import MarketingAgent, MarketingPromptGenerator
from src.agent.trading import TradingAgent, TradingPromptGenerator
from src.container import ContainerManager
from src.datatypes import StrategyData
from src.db import APIDB
from src.flows.marketing import unassisted_flow as marketing_unassisted_flow
from src.flows.trading import assisted_flow as trading_assisted_flow
from src.flows.trading import unassisted_flow as trading_unassisted_flow
from src.genner import get_genner
from src.helper import services_to_envs, services_to_prompts
from src.manager import ManagerClient
from src.rag import StrategyRAG
from src.sensor.marketing import MarketingSensor
from src.sensor.trading import TradingSensor
from src.summarizer import get_summarizer
from src.twitter import TweepyTwitterClient

load_dotenv()

# Research tools
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY") or ""
TWITTER_API_SECRET = os.getenv("TWITTER_API_KEY_SECRET") or ""
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN") or ""
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN") or ""
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET") or ""
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY") or ""
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY") or ""
INFURA_PROJECT_ID = os.getenv("INFURA_PROJECT_ID") or ""

# LLM Keys
DEEPSEEK_OPENROUTER_API_KEY = os.getenv("DEEPSEEK_OPENROUTER_API_KEY") or ""
DEEPSEEK_DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_DEEPSEEK_API_KEY") or ""
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or ""
OAI_API_KEY = os.getenv("OAI_API_KEY") or ""

# Our services
MANAGER_SERVICE_URL = os.getenv("MANAGER_SERVICE_URL") or ""
DB_SERVICE_URL = os.getenv("DB_SERVICE_URL") or ""
DEEPSEEK_LOCAL_SERVICE_URL = os.getenv("DEEPSEEK_LOCAL_SERVICE_URL") or ""
VAULT_SERVICE_URL = os.getenv("VAULT_SERVICE_URL") or ""
TXN_SERVICE_URL = os.getenv("TXN_SERVICE_URL") or ""
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL") or ""

# Our services keys
MANAGER_SERVICE_API_KEY = os.getenv("MANAGER_SERVICE_URL") or ""
DB_SERVICE_API_KEY = os.getenv("DB_SERVICE_API_KEY") or ""
DEEPSEEK_LOCAL_API_KEY = os.getenv("DEEPSEEK_LOCAL_API_KEY") or ""
VAULT_API_KEY = os.getenv("VAULT_API_KEY") or ""
TXN_SERVICE_API_KEY = os.getenv("TXN_SERVICE_API_KEY") or ""
RAG_SERVICE_API_KEY = os.getenv("RAG_SERVICE_API_KEY") or ""

# Clients Setup
deepseek_or_client = OpenAI(
	base_url="https://openrouter.ai/api/v1", api_key=DEEPSEEK_OPENROUTER_API_KEY
)
deepseek_local_client = OpenAI(
	base_url=DEEPSEEK_LOCAL_SERVICE_URL, api_key=DEEPSEEK_LOCAL_API_KEY
)
deepseek_deepseek_client = OpenAI(
	base_url="https://api.deepseek.com", api_key=DEEPSEEK_DEEPSEEK_API_KEY
)
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
oai_client = OpenAI(api_key=OAI_API_KEY)


def setup_trading_agent_flow(
	fe_data: dict, session_id: str, agent_id: str, assisted=True
) -> Tuple[TradingAgent, List[str], Callable[[StrategyData | None, str | None], None]]:
	role = fe_data["role"]
	services_used = fe_data["research_tools"]
	trading_instruments = fe_data["trading_instruments"]
	metric_name = fe_data["metric_name"]
	notif_sources = fe_data["notifications"]
	time_ = fe_data["time"]

	in_con_env = services_to_envs(services_used)
	apis = services_to_prompts(services_used)
	db = APIDB(base_url=DB_SERVICE_URL, api_key=DB_SERVICE_API_KEY)
	if fe_data['model'] == 'deepseek':
		fe_data['model'] = 'deepseek_or'
	genner = get_genner(
		fe_data["model"],
		deepseek_deepseek_client=deepseek_deepseek_client,
		deepseek_or_client=deepseek_or_client,
		deepseek_local_client=deepseek_local_client,
		anthropic_client=anthropic_client,
		stream_fn=lambda token: manager_client.push_token(token),
	)
	prompt_generator = TradingPromptGenerator(prompts=fe_data["prompts"])
	sensor = TradingSensor(
		agent_id=agent_id,
		infura_project_id=INFURA_PROJECT_ID,
		etherscan_api_key=ETHERSCAN_API_KEY,
		vault_base_url=VAULT_SERVICE_URL,
		vault_api_key=VAULT_API_KEY,
	)
	container_manager = ContainerManager(
		docker.from_env(),
		"agent-executor",
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
		agent_id=agent_id,
		sensor=sensor,
		genner=genner,
		container_manager=container_manager,
		prompt_generator=prompt_generator,
		db=db,
		rag=rag,
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
			txn_service_url=TXN_SERVICE_URL,
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
			txn_service_url=TXN_SERVICE_URL,
			summarizer=summarizer,
		)

	def wrapped_flow(prev_strat, notif_str):
		return flow_func(agent=agent, prev_strat=prev_strat, notif_str=notif_str)

	return agent, notif_sources, wrapped_flow


def setup_marketing_agent_flow(
	fe_data: dict, session_id: str, agent_id: str
) -> Tuple[
	MarketingAgent, List[str], Callable[[StrategyData | None, str | None], None]
]:
	role = fe_data["role"]
	time_ = fe_data["time"]
	metric_name = fe_data["metric_name"]
	notif_sources = fe_data["notifications"]
	services_used = fe_data["research_tools"]

	in_con_env = services_to_envs(services_used)
	apis = services_to_prompts(services_used)
	db = APIDB(base_url=DB_SERVICE_URL, api_key=DB_SERVICE_API_KEY)

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
	if fe_data['model'] == 'deepseek':
		fe_data['model'] = 'deepseek_or'
	genner = get_genner(
		fe_data["model"],
		deepseek_deepseek_client=deepseek_deepseek_client,
		deepseek_or_client=deepseek_or_client,
		deepseek_local_client=deepseek_local_client,
		anthropic_client=anthropic_client,
		stream_fn=lambda token: manager_client.push_token(token),
	)
	container_manager = ContainerManager(
		docker.from_env(),
		"agent-executor",
		"./code",
		in_con_env=in_con_env,
	)
	prompt_generator = MarketingPromptGenerator(fe_data["prompts"])

	previous_strategies = db.fetch_all_strategies(agent_id)
	rag = StrategyRAG(
		agent_id=agent_id,
		oai_client=oai_client,
		strategies=previous_strategies,
		storage_dir="./rag/trading",
	)

	agent = MarketingAgent(
		agent_id=agent_id,
		db=db,
		sensor=sensor,
		genner=genner,
		container_manager=container_manager,
		prompt_generator=prompt_generator,
		rag=rag,
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
		print("Usage: python main.py [trading|marketing] [session_id] [agent_id]")
		agent_type = "trading"
		session_id = "test_session_id"
		agent_id = "phi"
	else:
		agent_type = sys.argv[1]
		session_id = sys.argv[2]
		agent_id = sys.argv[3]

	manager_client = ManagerClient(MANAGER_SERVICE_URL, session_id)

	payload = json.dumps(
		{
			"session_id": session_id,
			"agent_id": agent_id,
			"started_at": datetime.datetime.now().isoformat(),
			"status": "running",
		}
	)

		# Check if the agent session already exists
	session_id_response = requests.post("https://superior-crud-api.fly.dev/api_v1/agent_sessions/get", json={"session_id": session_id, "agent_id": agent_id})
	session_id_response.raise_for_status()
	session_id_data = session_id_response.json()
	
	if session_id_data["data"]:
		_ = requests.post("https://superior-crud-api.fly.dev/api_v1/agent_sessions/update", json={"session_id": session_id, "agent_id": agent_id, "status": "running"})
	else:
		headers = {"x-api-key": DB_SERVICE_API_KEY, "Content-Type": "application/json"}
		response = requests.request(
			"POST",
			f"{DB_SERVICE_URL}/agent_sessions/create",
			headers=headers,
			data=payload,
		)
		logger.info(response.text)
		assert response.status_code == 200

	fe_data = manager_client.fetch_fe_data(agent_type)
	logger.info(f"Running {agent_type} agent for session {session_id}")

	if agent_type == "trading":
		agent, notif_sources, flow = setup_trading_agent_flow(
			fe_data, session_id, agent_id
		)

		flow(None, None)
		logger.info("Waiting for 15 seconds...")
		time.sleep(15)

		while True:
			prev_strat = agent.db.fetch_latest_strategy(agent.agent_id)
			logger.info(f"Previous strat is {prev_strat}")

			current_notif = agent.db.fetch_latest_notification_str(notif_sources)
			logger.info(f"Latest notification is {current_notif}")

			agent.rag.add_strategy(prev_strat)
			logger.info("Added the previous strat onto the RAG manager")

			flow(prev_strat, None)

			logger.info("Waiting for 15 seconds...")
			time.sleep(15)

	elif agent_type == "marketing":
		agent, notif_sources, flow = setup_marketing_agent_flow(
			fe_data, session_id, agent_id
		)

		flow(None, None)
		logger.info("Waiting for 15 seconds...")
		time.sleep(15)

		while True:
			prev_strat = agent.db.fetch_latest_strategy(agent.agent_id)
			logger.info(f"Previous strat is {prev_strat}")

			current_notif = agent.db.fetch_latest_notification_str(notif_sources)
			logger.info(f"Latest notification is {current_notif}")

			agent.rag.add_strategy(prev_strat)
			logger.info("Added the previous strat onto the RAG manager")

			flow(prev_strat, None)

			logger.info("Waiting for 15 seconds...")
			time.sleep(15)
	else:
		logger.error(f"Unknown agent type: {agent_type}")
		sys.exit(1)
