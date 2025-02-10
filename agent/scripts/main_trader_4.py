from collections.abc import Callable
import json
import os
import sys
import time
from pprint import pformat
from typing import Any, List

import requests
from anthropic import Anthropic
from anthropic import Anthropic as DeepSeekClient
from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI as DeepSeek

import docker
from result import UnwrapError
from src.agent.trading_2 import TradingAgent, TradingPromptGenerator
from src.container import ContainerManager
from src.datatypes import StrategyData
from src.db.trading_2 import TradingDBAPI
from src.genner import get_genner
from src.helper import services_to_envs, services_to_prompts
from src.sensor.trading import TradingSensor

load_dotenv()

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


def assisted_flow(
	agent: TradingAgent,
	apis: List[str],
	trading_instruments: List[str],
	metric_name: str,
	prev_strat: StrategyData | None,
):
	"""
	General Algorithm:
	- Initiate chat history with system prompt consisting of
	- Initiate user prompt to generate reasoning
	"""
	agent.reset()
	logger.info("Reset agent")

	metric_state = str(agent.sensor.get_metric_fn(metric_name)())

	logger.info("Using metric: {metric_name}")
	logger.info(f"Current state of the metric: {metric_state}")
	agent.chat_history = agent.prepare_system(
		metric_name=metric_name, metric_state=metric_state
	)
	logger.info("Initialized system prompt")

	logger.info("Attempt to generate strategy...")
	code = ""
	regen = False
	err_ = ""
	for i in range(3):
		try:
			if regen:
				if not prev_strat:
					logger.info("Regenning on first strategy...")
				else:
					logger.info("Regenning on strategy..")

			if not prev_strat:
				result = agent.gen_strategy_on_first(apis)
			else:
				result = agent.gen_strategy(
					cur_environment="notification",
					prev_strategy=prev_strat.summarized_desc,
					prev_strategy_result=prev_strat.strategy_result,
					apis=apis,
				)

			strategy_output, new_ch = result.unwrap()
			agent.chat_history += new_ch

			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on strategy generation, err: \n{e}")
			else:
				logger.error(f"Failed on first strategy generation, err: \n{e}")
			regen = True
			err_ += f"\n{str(e)}"

	logger.info("Succeeded strategy generation")
	logger.info(f"Strategy generation :\n{strategy_output}")

	logger.info("Attempt to generate account research code...")
	code = ""
	regen = False
	err_ = ""
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on account research")
				regen_result = agent.gen_better_code(code, err_)
				code, new_ch = regen_result.unwrap()
				agent.chat_history += new_ch
			else:
				account_research_code_result = agent.gen_account_research_code()
				code, new_ch = account_research_code_result.unwrap()
				agent.chat_history += new_ch

			code_execution_result = agent.container_manager.run_code_in_con(
				code, "trader_market_account_research_on_daily"
			)
			address_research, _ = code_execution_result.unwrap()

			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on address research, err: \n{e}")
			else:
				logger.error(f"Failed on first address research code, err: \n{e}")
			regen = True
			err_ += f"\n{str(e)}"

	logger.info("Succeeded address research")
	logger.info(f"Address research \n{address_research}")

	logger.info("Generating some trading code")
	code = ""
	regen = False
	err = ""
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on trading code...")
				regen_result = agent.gen_better_code(code, err)
				code, new_ch = regen_result.unwrap()
				agent.chat_history += new_ch
			else:
				gen_code_result = agent.gen_trading_code(
					strategy_output=strategy_output,
					address_research=address_research,
					apis=apis,
					trading_instruments=trading_instruments,
				)

				code, new_ch = gen_code_result.unwrap()
				agent.chat_history += new_ch

			code_execution_result = agent.container_manager.run_code_in_con(
				code, "trader_trade_on_daily"
			)
			output, reflected_code = code_execution_result.unwrap()

			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on trading code, err: \n{e}")
			else:
				logger.error(f"Failed on first trading code, err: \n{e}")
			regen = True
			err_ += f"\n{str(e)}"

	logger.info(f"Code finished executed with success! with the output of: \n{output}")
	logger.info("Checking latest portfolio...")
	time.sleep(10)
	portfolio = agent.sensor.get_portfolio_status()
	logger.info(f"Latest Portofolio: {pformat(portfolio)}")
	logger.info("Saving current session chat history into the retraining database...")


if __name__ == "__main__":
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
		"research_tools": [
			"CoinGecko",
			"DuckDuckGo",
			"Etherscan",
			"Infura",
		],
		"prompts": {},  # Ensure this stays as a dictionary
		"trading_instruments": ["spot"],
		"metric_name": "wallet",
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

	metric_name = fe_data["metric_name"]
	agent_id = fe_data["agent_id"]
	services_used = fe_data["research_tools"]
	trading_instruments = fe_data["trading_instruments"]
	metric_name = fe_data["metric_name"]

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
	db = None
	container_manager = ContainerManager(
		docker_client,
		"twitter_agent_executor",
		"./code",
		in_con_env=services_to_envs(services_used),
	)

	agent = TradingAgent(
		sensor=sensor,
		genner=genner,
		container_manager=container_manager,
		prompt_generator=prompt_generator,
	)

	db = TradingDBAPI(base_url="https://superior-crud-api.fly.dev")

	prev_strat = db.fetch_latest_strategy(agent_id)

	assisted_flow(
		agent=agent,
		apis=apis,
		trading_instruments=trading_instruments,
		metric_name=metric_name,
		prev_strat=prev_strat,
	)
