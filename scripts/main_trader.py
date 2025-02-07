import json
import os
import sys
import time
from pprint import pformat
from typing import List

import requests
from anthropic import Anthropic
from anthropic import Anthropic as DeepSeekClient
from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI as DeepSeek

import docker
from result import UnwrapError
from src.agent.trading import TradingAgent, TradingPromptGenerator
from src.container import ContainerManager
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
CLAUDE_KEY = os.getenv("CLAUDE_KEY") or ""
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY") or ""
DEEPSEEK_KEY_2 = os.getenv("DEEPSEEK_KEY_2") or ""
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or ""


def on_daily(
	agent: TradingAgent,
	apis: List[str],
	trading_instruments: List[str],
):
	"""
	General Algorithm:
	- Initiate chat history with system prompt consisting of
	- Initiate user prompt to generate reasoning
	"""
	agent.reset()
	logger.info("Reset agent")

	prev_strat = None
	portfolio = agent.sensor.get_portfolio_status()
	logger.info(f"Portofolio: {pformat(portfolio)}")
	agent.chat_history = agent.prepare_system(str(portfolio), prev_strat)
	logger.info("Initiated system prompt")

	logger.info("Attempt to generate market research code...")
	code = ""
	regen = False
	err_ = ""
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on market research")
				regen_result = agent.gen_better_code(code, err_)
				code, new_ch = regen_result.unwrap()
				agent.chat_history += new_ch
			else:
				market_research_code_result = agent.gen_market_research_code(
					str(portfolio),
					apis,
				)
				code, new_ch = market_research_code_result.unwrap()
				agent.chat_history += new_ch

			code_execution_result = agent.container_manager.run_code_in_con(
				code, "trader_market_research_on_daily"
			)
			market_research, _ = code_execution_result.unwrap()

			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on market research, err: \n{e}")
			else:
				logger.error(f"Failed on first market research code, err: \n{e}")
			regen = True
			err_ += f"\n{str(e)}"

	logger.info("Succeeded market research")
	logger.info(f"Market research :\n{market_research}")

	logger.info("Attempt to generate some strategy")
	err_ = ""
	regen = False
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning some strat")
			else:
				logger.info("Generating some strategy")
			gen_result = agent.gen_strategy(str(portfolio), market_research)
			strategy, new_ch = gen_result.unwrap()
			agent.chat_history += new_ch

			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on strategy gen: \n{e}")
			else:
				logger.error("Failed on first strategy gen: \n{e}")
			regen = True
			err_ += f"\n{str(e)}"
	logger.info(f"Strategy generated: \n{strategy}")

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
			account_research, _ = code_execution_result.unwrap()

			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on account research, err: \n{e}")
			else:
				logger.error(f"Failed on first account research code, err: \n{e}")
			regen = True
			err_ += f"\n{str(e)}"

	logger.info("Succeeded account research")
	logger.info(f"Account research \n{account_research}")

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
					account_research, trading_instruments
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


def on_notification(
	agent: TradingAgent,
	apis: List[str],
	notification: str,
	trading_instruments: List[str],
):
	agent.reset()
	logger.info("Reset agent")

	prev_strat = None
	if prev_strat is None:
		logger.info(
			"We have no strategy picked yet, meaning on_daily has not run yet, stopping..."
		)
		return

	logger.info(f"Latest strategy is {prev_strat}")
	portfolio = agent.sensor.get_portfolio_status()
	logger.info(f"Portofolio: {pformat(portfolio)}")
	new_ch = agent.prepare_system(str(portfolio), prev_strat)
	agent.chat_history += new_ch
	logger.info("Initiated system prompt")

	logger.info(
		f"Attempt to generate market research code based on notification {notification}..."
	)
	code = ""
	regen = False
	err_acc = ""
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on market research on notification")
				regen_result = agent.gen_better_code(code, err_acc)
				code, new_ch = regen_result.unwrap()
				agent.chat_history += new_ch
			else:
				account_research_code_result = agent.gen_market_research_on_notif_code(
					str(portfolio),
					notification,
					apis,
					str(prev_strat),
				)
				code, new_ch = account_research_code_result.unwrap()
				agent.chat_history += new_ch

			code_execution_result = agent.container_manager.run_code_in_con(
				code, "trader_market_research_on_notification"
			)
			market_research, _ = code_execution_result.unwrap()

			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(
					f"Regen failed on market research code, caused by err: \n{e}"
				)
			else:
				logger.error(f"Failed on first market research code genning: \n{e}")
			err_acc += f"\n{str(e)}"

			regen = True
	logger.info(f"Succeeded market research on notification {notification}")
	logger.info(f"Market research on notification :\n{market_research}")

	logger.info("Attempt to generate account research code...")
	code = ""
	regen = False
	err_ = ""
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on account research")
				regen_result = agent.gen_better_code(code, err_acc)
				code, new_ch = regen_result.unwrap()
				agent.chat_history += new_ch
			else:
				account_research_code_result = agent.gen_account_research_code()
				code, new_ch = account_research_code_result.unwrap()
				agent.chat_history += new_ch

			code_execution_result = agent.container_manager.run_code_in_con(
				code, "trader_market_account_research_on_daily"
			)
			account_research, _ = code_execution_result.unwrap()

			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on account research: \n{e}")
			else:
				logger.error(f"Failed on first account research code generation: \n{e}")
			regen = True
			err_ += f"\n{str(e)}"
	logger.info("Succeeded account research")
	logger.info(f"Account research \n{account_research}")

	logger.info("Generating some trading code")
	code = ""
	regen = False
	err = ""
	success = False
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on trading code...")
				regen_result = agent.gen_better_code(code, err)
				code, new_ch = regen_result.unwrap()
				agent.chat_history += new_ch
			else:
				gen_code_result = agent.gen_trading_code(
					account_research, trading_instruments
				)
				code, new_ch = gen_code_result.unwrap()
				agent.chat_history += new_ch

			code_execution_result = agent.container_manager.run_code_in_con(
				code, "trader_trade_on_daily"
			)
			output, reflected_code = code_execution_result.unwrap()

			success = True
			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error("Regen failed on trading code generation, \n")
			else:
				logger.error("Failed on first trading code generation: \n")
			regen = True
			err += f"\n{str(e)}"

	if success:
		logger.info(
			f"Code finished executed with success! with the output of: \n{output}"
		)
		logger.info("Checking latest portfolio...")
		time.sleep(10)
	else:
		logger.info(
			f"Code finished executing with no success... Caused by series of error: \n{err}"
		)

	portfolio = agent.sensor.get_portfolio_status()
	logger.info(f"Latest Portofolio: {pformat(portfolio)}")
	logger.info("Saving current session chat history into the retraining database...")


if __name__ == "__main__":
	deepseek_client = DeepSeek(
		base_url="https://openrouter.ai/api/v1", api_key=DEEPSEEK_KEY
	)
	deepseek_2_client = DeepSeekClient(api_key=DEEPSEEK_KEY_2)
	anthropic_client = Anthropic(api_key=CLAUDE_KEY)

	HARDCODED_BASE_URL = "http://34.87.43.255:4999"

	# collect args[1] as session id
	session_id = sys.argv[1]

	logger.info(f"Session ID: {session_id}")

	# Connect to SSE endpoint to get session logs
	url = f"{HARDCODED_BASE_URL}/sessions/{session_id}/logs"
	headers = {"Accept": "text/event-stream"}

	fe_data = {
		"model": "deepseek_2",
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
				# logger.error(f"Decoded line: {decoded_line}")
				if decoded_line.startswith("data: "):
					data = json.loads(decoded_line[6:])  # Skip "data: " prefix
					if "logs" in data:  # Only process messages containing logs
						log_entries = data["logs"].strip().split("\n")
						if log_entries:
							first_log = json.loads(log_entries[0])
							if first_log["type"] == "request":
								logger.error("Initial prompt:")
								logger.error(json.dumps(first_log["payload"], indent=2))
								fe_data = json.loads(
									json.dumps(first_log["payload"], indent=2)
								)
								break
	except Exception as e:
		print(f"Error fetching session logs: {e}")

	default_prompts = TradingPromptGenerator.get_default_prompts()

	for key, value in default_prompts.items():
		if key in fe_data["prompts"]:
			continue

		fe_data["prompts"][key] = value

	services_used = fe_data["research_tools"]
	trading_instruments = fe_data["trading_instruments"]
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

	on_daily(agent, apis, trading_instruments)
