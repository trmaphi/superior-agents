import json
import os
import sys

import requests
from anthropic import Anthropic
from anthropic import Anthropic as DeepSeekClient
from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI as DeepSeek

import docker
from src.agent.trading_2 import TradingAgent, TradingPromptGenerator
from src.container import ContainerManager
from src.db import APIDB
from src.flows.trading import assisted_flow
from src.genner import get_genner
from src.helper import services_to_envs, services_to_prompts
from src.llm_functions import get_summarizer
from src.sensor.trading import TradingSensor

load_dotenv()

STARTER_STR = os.getenv("STARTER_STR") or "Starting!!!"
ENDING_STR = os.getenv("ENDING_STR") or "Ending!!!"

TWITTER_API_KEY = os.getenv("API_KEY") or ""
TWITTER_API_SECRET = os.getenv("API_KEY_SECRET") or ""
TWITTER_BEARER_TOKEN = os.getenv("BEARER_TOKEN") or ""
TWITTER_ACCESS_TOKEN = os.getenv("ACCESS_TOKEN") or ""
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET") or ""

os.environ["TWITTER_API_KEY"] = TWITTER_API_KEY
os.environ["TWITTER_API_SECRET"] = TWITTER_API_SECRET
os.environ["TWITTER_ACCESS_TOKEN"] = TWITTER_ACCESS_TOKEN
os.environ["TWITTER_ACCESS_TOKEN_SECRET"] = TWITTER_ACCESS_TOKEN_SECRET
os.environ["TWITTER_BEARER_TOKEN"] = TWITTER_BEARER_TOKEN

ETHER_ADDRESS = os.getenv("ETHER_ADDRESS") or ""
ETHER_PRIVATE_KEY = os.getenv("ETHER_PRIVATE_KEY") or ""

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

	# collect args[1] as session id
	session_id = sys.argv[1]

	logger.info(f"Session ID: {session_id}")

	# Connect to SSE endpoint to get session logs
	url = f"{HARDCODED_BASE_URL}/sessions/{session_id}/logs"
	headers = {"Accept": "text/event-stream"}
	logger.info("Trading start")

	# Initialize fe_data with default values
	fe_data = {
		"model": "deepseek_2",
		"agent_id": "default_trading_agent",  
		"metric_name": "wallet",  
		"research_tools": [
			"CoinGecko",  
			"DuckDuckGo",  
			"Etherscan",  
			"Infura",  
		],
		"prompts": {},  
		"trading_instruments": ["spot"],  
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

								if "trading_instruments" in payload and isinstance(
									payload["trading_instruments"], list
								):
									fe_data["trading_instruments"] = payload[
										"trading_instruments"
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
		default_prompts = TradingPromptGenerator.get_default_prompts()
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
		default_prompts = TradingPromptGenerator.get_default_prompts()
		fe_data["prompts"].update(default_prompts)

	logger.info(f"Final prompts: {fe_data["prompts"]}")

	agent_id = fe_data["agent_id"]
	role = fe_data["role"]
	services_used = fe_data["research_tools"]
	trading_instruments = fe_data["trading_instruments"]
	metric_name = fe_data["metric_name"]
	time = fe_data["time"]

	model_name = "deepseek_2"
	in_con_env = services_to_envs(services_used)
	apis = services_to_prompts(services_used)

	genner = get_genner(
		model_name,
		deepseek_client=deepseek_client,
		anthropic_client=anthropic_client,
		deepseek_2_client=deepseek_2_client,
	)
	prompt_generator = TradingPromptGenerator(
		prompts=fe_data["prompts"],
	)

	docker_client = docker.from_env()
	sensor = TradingSensor(
		eth_address=str(os.getenv("ETHER_ADDRESS")),
		infura_project_id=str(os.getenv("INFURA_PROJECT_ID")),
		etherscan_api_key=str(os.getenv("ETHERSCAN_KEY")),
	)
	container_manager = ContainerManager(
		docker_client,
		"twitter_agent_executor",
		"./code",
		in_con_env=services_to_envs(services_used),
	)
	db = APIDB(base_url="https://superior-crud-api.fly.dev")

	agent = TradingAgent(
		id=agent_id,
		sensor=sensor,
		genner=genner,
		container_manager=container_manager,
		prompt_generator=prompt_generator,
		db=db,
	)

	summarizer = get_summarizer(genner)

	prev_strat = db.fetch_latest_strategy(agent_id)

	assisted_flow(
		agent=agent,
		session_id=session_id,
		role=role,
		time=time,
		apis=apis,
		trading_instruments=trading_instruments,
		metric_name=metric_name,
		prev_strat=prev_strat,
		summarizer=summarizer,
	)

	logger.info(ENDING_STR)
