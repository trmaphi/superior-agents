import datetime
import os
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

from anthropic import Anthropic as DeepSeekClient
from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI as DeepSeek
from pprint import pformat


import docker
from result import UnwrapError
from src.agent.trading2 import TradingAgent
from src.container import ContainerManager
from src.datatypes import StrategyData
from src.datatypes.trading import TradingAgentState
from src.db.trading import TradingDB
from src.genner import get_genner
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
DEEPSEEK_KEY_2 = os.getenv("DEEPSEEK_KEY_2") or ""


def on_daily(agent: TradingAgent):
	"""
	General Algorithm:
	- Initiate system prompt
		- SENSOR: Get portfolio data and assign to system prompt
		- SENSOR: Get market research data and assign to user prompt
	- Initiate user prompt to generate reasoning
		- SELF: Initiate a strategy to use and assign to user prompt
			- If there's no cached strategy or all cached strategies have been used, generate new strategies
			- If there's a cached strategy that hasn't been used, use it
	- GEN REASON: Assistant to reply with reasonings as of why strategy might work

	Trading Algorithm:
	- Loop until max 5 times
		- Initiate user prompt for assistant to generate code from previous reasoning
		- GEN CODE: Assistant to reply with trade execution code
		- Initiate user prompt for assistant to generate reasoning of why trade will work or not
		- GEN REASON: Assistant to reply with reasonings
		- If
			- Code gen fails, continue
			- Code gen fails more than 5 times, summarize the reason why it breaks, break
			- Code gen works, summarize the reason of why it works, break
	"""
	agent.reset()
	logger.info("Reset agent")

	prev_strat = agent.db.get_latest_tried_strategy()
	portfolio = agent.sensor.get_portfolio_status()
	logger.info(f"Portofolio: {pformat(portfolio)}")
	agent.chat_history = agent.prepare_system(str(portfolio), prev_strat)
	logger.info("Initiated system prompt")

	logger.info("Attempt to generate market research code...")
	code = ""
	regen = False
	err_ = ""
	market_research = "Failed to generate market research after all retries"
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on market research")
				regen_result = agent.gen_better_code(code, err_)
				code, new_ch = regen_result.unwrap()
				agent.chat_history += new_ch
			else:
				account_research_code_result = agent.gen_market_research_code(
					str(portfolio)
				)
				code, new_ch = account_research_code_result.unwrap()
				agent.chat_history += new_ch

			code_execution_result = agent.container_manager.run_code_in_con(
				code, "trader_market_research_on_daily"
			)
			market_research, _ = code_execution_result.unwrap()

			break
		except Exception as e:
			logger.error("Regen failed on market research")
			regen = True
			err_ += f"\n{str(e)}"
	logger.info("Succeeded market research")
	logger.info(f"Market research :\n{market_research}")

	logger.info("Attempt to generate account research code...")
	code = ""
	regen = False
	err_ = ""
	account_research = "Failed to generate account research after all retries"
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
		except Exception as e:
			logger.error("Regen failed on account research")
			regen = True
			err_ += f"\n{str(e)}"
	logger.info("Succeeded account research")
	logger.info(f"Account research \n{account_research}")

	logger.info("Attempt to generate some strategy")
	err_ = ""
	regen = False
	for i in range(3):
		try:
			logger.info("Generating some strategy")
			gen_result = agent.gen_strategy(str(portfolio), market_research)
			strategy, new_ch = gen_result.unwrap()
			agent.chat_history += new_ch

			break
		except Exception as e:
			if err_:
				logger.error("Regen failed on strategy gen")
			regen = True
			err_ += f"\n{str(e)}"
	logger.info(f"Strategy generated: \n{strategy}")

	logger.info("Generating some trading code")
	code = ""
	regen = False
	err = ""
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning")
				regen_result = agent.gen_better_code(code, err)
				code, new_ch = regen_result.unwrap()
				agent.chat_history += new_ch
			else:
				gen_code_result = agent.gen_trading_code(account_research)
				code, new_ch = gen_code_result.unwrap()
				agent.chat_history += new_ch

			code_execution_result = agent.container_manager.run_code_in_con(
				code, "trader_trade_on_daily"
			)
			output, reflected_code = code_execution_result.unwrap()

			break
		except Exception as e:
			regen = True
			err += f"\n{str(e)}"
			break

	output, reflected_code = code_execution_result.unwrap()
	logger.info(f"Latest Portfolio: {pformat(portfolio)}")
	logger.info("Saving current session chat history into the retraining database...")


MODEL = "deepseek"

if __name__ == "__main__":
	# deepseek_client = DeepSeek(
	# 	base_url="https://openrouter.ai/api/v1",
	# 	api_key=DEEPSEEK_KEY
	# )
	# deepseek_client = DeepSeek(
	# 	base_url="https://openrouter.ai/api/v1",
	# 	api_key=DEEPSEEK_OPENROUTER_KEY,
	# )
	deepseek_client = DeepSeekClient(api_key=DEEPSEEK_KEY_2)

	genner = get_genner("deepseek_2", deepseek_2_client=deepseek_client)

	docker_client = docker.from_env()
	sensor = TradingSensor(
		eth_address=str(os.getenv("ETHER_ADDRESS")),
		infura_project_id=str(os.getenv("INFURA_PROJECT_ID")),
		etherscan_api_key=str(os.getenv("ETHERSCAN_KEY")),
	)
	db = TradingDB()

	container_manager = ContainerManager(
		docker_client,
		"twitter_agent_executor",
		"./code",
		in_con_env={
			"TWITTER_API_KEY": TWITTER_API_KEY,
			"TWITTER_API_SECRET": TWITTER_API_SECRET,
			"TWITTER_BEARER_TOKEN": TWITTER_BEARER_TOKEN,
			"TWITTER_ACCESS_TOKEN": TWITTER_ACCESS_TOKEN,
			"TWITTER_ACCESS_TOKEN_SECRET": TWITTER_ACCESS_TOKEN_SECRET,
			"COINGECKO_KEY": COINGECKO_KEY,
			"INFURA_PROJECT_ID": INFURA_PROJECT_ID,
			"ETHERSCAN_KEY": ETHERSCAN_KEY,
			"ETHER_ADDRESS": ETHER_ADDRESS,
			"ETHER_PRIVATE_KEY": ETHER_PRIVATE_KEY,
		},
	)

	agent = TradingAgent(
		db=db, sensor=sensor, genner=genner, container_manager=container_manager
	)

	on_daily(agent)
