import os
import time
from typing import List

from anthropic import Anthropic as DeepSeekClient
from anthropic import Anthropic
from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI as DeepSeek
from pprint import pformat


import docker
from src.agent.trading3 import TradingAgent, TradingType
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


def on_daily(agent: TradingAgent, personality: str, apis: List[str]):
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
	agent.chat_history = agent.prepare_system(personality, str(portfolio), prev_strat)
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
		except Exception as e:
			if regen:
				logger.error("Regen failed on market research")
			else:
				logger.error(f"Failed on first market research code: \n{e}")
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
		except Exception as e:
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
		except Exception as e:
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
			if regen:
				logger.error(f"Regen failed on trading code generation, \n{e}")
			else:
				logger.error(f"Failed on first trading code generation: \n{e}")
			regen = True
			err += f"\n{str(e)}"

	logger.info(f"Code finished executed with success! with the output of: \n{output}")
	logger.info("Checking latest portfolio...")
	time.sleep(10)
	portfolio = agent.sensor.get_portfolio_status()
	logger.info(f"Latest Portofolio: {pformat(portfolio)}")
	logger.info("Saving current session chat history into the retraining database...")


def on_notification(
	agent: TradingAgent, personality: str, apis: List[str], notification: str
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
	new_ch = agent.prepare_system(personality, str(portfolio), prev_strat)
	agent.chat_history += new_ch
	logger.info("Initiated system prompt")

	logger.info(
		f"Attempt to generate market research code based on notification {notification}..."
	)
	code = ""
	regen = False
	err_ = ""
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on market research on notification")
				regen_result = agent.gen_better_code(code, err_)
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
		except Exception as e:
			if regen:
				logger.error(
					f"Regen failed on market research on notification, err: \n{e}"
				)
			else:
				logger.error(
					f"Failed on first market research code on notification: \n{e}"
				)
			regen = True
			err_ += f"\n{str(e)}"
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

			success = True
			break
		except Exception as e:
			if regen:
				logger.error(f"Regen failed on trading code generation, \n{e}")
			else:
				logger.error(f"Failed on first trading code generation: \n{e}")
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
	# deepseek_client = DeepSeek(
	# 	base_url="https://openrouter.ai/api/v1",
	# 	api_key=DEEPSEEK_KEY
	# )
	# deepseek_client = DeepSeek(
	# 	base_url="https://openrouter.ai/api/v1",
	# 	api_key=DEEPSEEK_OPENROUTER_KEY,
	# )

	services_used = [
		"CoinGecko",
		"DuckDuckGo",
		"Etherscan",
		"Infura",
	]
	model_name = "claude"
	in_con_env = services_to_envs(services_used)
	apis = services_to_prompts(services_used)

	genner = get_genner(
		model_name,
		deepseek_client=deepseek_client,
		anthropic_client=anthropic_client,
		deepseek_2_client=deepseek_2_client,
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
		sensor=sensor, genner=genner, container_manager=container_manager, trading_type=TradingType.FUTURES
	)

	on_daily(agent, "You are a degen speculative tokens trading agent.", apis)
