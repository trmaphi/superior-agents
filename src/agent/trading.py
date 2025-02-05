from textwrap import dedent
from typing import List, Tuple
from loguru import logger
from result import Result, Ok, Err

from src.container import ContainerManager
from src.datatypes import StrategyData
from src.genner.Base import Genner
from src.sensor.trading import TradingSensor
from src.types import ChatHistory, Message


class TradingPromptGenerator:
	@staticmethod
	def generate_system_prompt(
		portfolio: str, prev_strat: StrategyData | None, personality: str
	) -> str:
		portfolio_str = str(portfolio)
		prev_strat_str = str(prev_strat)

		return dedent(
			"""
			{personality}
			You are a trader whose ultimate goal is to be richer in 24 hours.
			Here is your current portofolio on Ethereum network:
			<Portofolio>
			{portfolio_str}
			</Portofolio>
			Yesterday you tried this strategy
			<Strategy>
			{strategy_str}
			</Strategy>
			You can only trade using 1INCH. 
			You will need to research what coins to buy and sell, and write code to do so using the 1INCH API and the ABIs provided.
			""".strip().format(
				personality=personality,
				portfolio_str=portfolio_str,
				strategy_str=prev_strat_str,
			)
		)

	@staticmethod
	def generate_research_code_prompt(portfolio: str, apis: List[str]) -> str:
		apis = (
			apis
			if len(apis) > 0
			else [
				"Coingecko (env variables COINGECKO_KEY)"
				"Etherscan (env variables ETHERSCAN_KEY)",
				"Twitter (env variables TWITTER_API_KEY, TWITTER_API_SECRET)"
				"DuckDuckGo (using the command line `ddgr`)",
			]
		)
		apis_str = ",\n".join(apis)

		return dedent(
			"""
			You are a degen speculative tokens trading agent, your goal is to be richer in 24 hrs than now. 
			Here is your current portfolio : 
			<Portofolio>
			{portfolio}
			</Portofolio>
			Yesterday you did not trade. 
			You have access to the following APIs : 
			<APIs>
			{apis_str}
			</APIs>
			and can use the Duck Duck Go `ddgr` command line search.
			Please write code like format below to use your resources to research the state of the market. 
			```python
			from dotenv import load_dotenv
			import ...

			load_dotenv()

			def main():
				....
			
			main()
			```
			""".strip()
		).format(portfolio=portfolio, apis_str=apis_str)

	# You just received the following news [notification].
	# Bearing in mind your portfolic [value and that your current strateay is [strategy],
	# please use the following APis to research how to respond."""

	@staticmethod
	def generate_research_code_on_notif_prompt(
		portfolio: str, notification: str, apis: List[str], strategy: str
	) -> str:
		apis = (
			apis
			if len(apis) > 0
			else [
				"Coingecko (env variables COINGECKO_KEY)"
				"Etherscan (env variables ETHERSCAN_KEY)",
				"Twitter (env variables TWITTER_API_KEY, TWITTER_API_SECRET)"
				"DuckDuckGo (using the command line `ddgr`)",
			]
		)
		apis_str = ",\n".join(apis)

		return dedent(
			"""
			You are a degen speculative tokens trading agent, your goal is to be richer in 24 hrs than now. 
			You have just received a notification :
			<Notification>
			{notification}
			</Notification>
			Bearing in mind your portfolic values : 
			<Portofolio>
			{portfolio}
			</Portofolio>
			And access to these API keys :
			<APIs>
			{apis_str}
			</APIs>
			Where this is your current strategy : 
			<Strategy>
			{strategy}
			</Strategy>
			Please write code like format below to use your resources to research the state of the market and on how to respond.
			```python
			from dotenv import load_dotenv
			import ...

			load_dotenv()

			def main():
				....
			
			main()
			```
			""".strip()
		).format(
			portfolio=portfolio,
			notification=notification,
			apis_str=apis_str,
			strategy=strategy,
		)

	@staticmethod
	def generate_address_research_code_prompt() -> str:
		return dedent(
			"""
			You are a degen speculative tokens trading agent, your goal is to be richer in 24 hrs than now. 
			Above is the result of your market research.
			For the coins mentioned above, please generate some code to get the actual ethereum address of those tokens or the wrapped equivalent.
			Use the Dexscreener API to find the token contract addresses if you do not know them.
			You are to generate like the format below :
			```python
			from dotenv import load_dotenv
			import ...

			load_dotenv()

			def main():
				....
			
			main()
			```
			Please generate the code.
			"""
		)

	@staticmethod
	def generate_strategy_prompt(portfolio: str, research: str) -> str:
		return dedent(
			"""
			You are a degen speculative tokens trading agent, your goal is to be richer in 24 hrs than now. 
			Here is your current portfolio on ethereum network: 
			<Portfolio>
			{portfolio}
			</Portfolio>
			Yesterday you did not trade. 
			You just learnt the following information: 
			<Research>
			{research}
			</Research>
			Decide what coin in the ethereum network you should buy today to maximise your chances of making money. You will trade on 1INCH using our API.
			Reason through your decision process below, formulating a strategy and explaining which coin(s) you will buy.
			""".strip()
		).format(portfolio=portfolio, research=research)

	@staticmethod
	def generate_trading_code_prompt(address_research: str):
		return dedent(
			"""
			You are a crypto trading agent, please generate some code to execute the above strategy.
			Above is the token research result that you can use.
			You are to generate code in this format below : 
			```python
			from dotenv import load_dotenv
			import ...

			def main():
				....
			
			main()
			```
			You are to use curl to perform swap on with our API :
			```bash
			# Swapping USDT to USDC
			curl -X POST "http://localhost:9009/api/v1/swap" \
			-H "Content-Type: application/json" \
			-d '{
				"token_in": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC example address
				"token_out": "0xdAC17F958D2ee523a2206206994597C13D831ec7", # USDT example address
				"amount_in": "1000000",  # 1 USDC (6 decimals)
				"slippage": 0.5
			}'
			```
			If your strategy requires you to trade, do it with this API. 
			Your code has to raise an exception, if the trade fails so we can detect it.
			Write only the code, and make sure it trades.
			""".strip()
		)

	@staticmethod
	def regen_code(previous_code: str, errors: str):
		return dedent(
			"""
			Given this errors
			<Errors>
			{errors}
			</Errors>
			And the code it's from
			<Code>
			{previous_code}
			</Code>
			You are to generate code that fixes the error but doesnt stray too much from the original code, in this format.
			```python
			from dotenv import load_dotenv
			import ...

			load_dotenv()

			def main():
				....
			
			main()
			```
			Please generate the code.
			"""
		).format(errors=errors, previous_code=previous_code)


class TradingAgent:
	def __init__(
		self,
		sensor: TradingSensor,
		genner: Genner,
		container_manager: ContainerManager,
	):
		self.sensor = sensor
		self.chat_history = ChatHistory()
		self.genner = genner
		self.container_manager = container_manager
		self.strategy = ""

	def reset(self) -> None:
		self.chat_history = ChatHistory()
		self.strategy = ""

	def prepare_system(
		self,
		personality: str,
		portfolio_data: str,
		yesterday_strat: StrategyData | None,
	):
		ctx_ch = ChatHistory(
			Message(
				role="system",
				content=TradingPromptGenerator.generate_system_prompt(
					portfolio_data, yesterday_strat, personality
				),
			)
		)

		return ctx_ch

	def gen_market_research_code(
		self, portfolio: str, apis: List[str]
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=TradingPromptGenerator.generate_research_code_prompt(
					portfolio, apis
				),
			)
		)
		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			logger.error(f"TradingAgent.gen_market_research_code, err: \n{err}")
			return Err(f"TradingAgent.gen_market_research_code, err: \n{err}")

		processed_codes, raw_response = gen_result.unwrap()
		logger.info(raw_response)
		ctx_ch.messages.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_market_research_on_notif_code(
		self, portfolio: str, notification: str, apis: List[str], cur_strat: str
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=TradingPromptGenerator.generate_research_code_on_notif_prompt(
					portfolio, notification, apis, cur_strat
				),
			)
		)
		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			logger.error(
				f"TradingAgent.gen_market_research_on_notif_code, err: \n{err}"
			)
			return Err(f"TradingAgent.gen_market_research_on_notif_code, err: \n{err}")

		processed_codes, raw_response = gen_result.unwrap()
		logger.info(raw_response)
		ctx_ch.messages.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_account_research_code(
		self,
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=TradingPromptGenerator.generate_address_research_code_prompt(),
			)
		)

		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			logger.error(f"TradingAgent.gen_account_research_code, err: \n{err}")
			return Err(f"TradingAgent.gen_account_research_code, err: \n{err}")

		processed_codes, raw_response = gen_result.unwrap()
		logger.info(raw_response)
		ctx_ch.messages.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_strategy(
		self, portfolio: str, research: str
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=TradingPromptGenerator.generate_strategy_prompt(
					portfolio, research
				),
			)
		)

		gen_result = self.genner.ch_completion(self.chat_history + ctx_ch)

		if err := gen_result.err():
			logger.error(f"TradingAgent.gen_strategy, err: \n{err}")
			return Err(f"TradingAgent.gen_strategy, err: \n{err}")

		response = gen_result.unwrap()
		ctx_ch.messages.append(Message(role="assistant", content=response))

		return Ok((response, ctx_ch))

	def gen_trading_code(
		self, address_research: str
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=TradingPromptGenerator.generate_trading_code_prompt(
					address_research
				),
			)
		)

		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			logger.error(f"TradingAgent.gen_market_research_code, err: \n{err}")
			return Err(f"TradingAgent.gen_market_research_code, err: \n{err}")

		processed_codes, raw_response = gen_result.unwrap()
		logger.info(raw_response)
		ctx_ch.messages.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_better_code(
		self, prev_code: str, errors: str
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=TradingPromptGenerator.regen_code(prev_code, errors),
			)
		)

		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			logger.error(f"TradingAgent.gen_better_code, err: \n{err}")
			return Err(f"TradingAgent.gen_better_code, err: \n{err}")

		processed_codes, raw_response = gen_result.unwrap()
		logger.info(raw_response)
		ctx_ch.messages.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_strategy_reasoning(self, strategy):
		pass

	def gen_code(self):
		pass

	def gen_code_retry_reasoning(self, output, err):
		pass
