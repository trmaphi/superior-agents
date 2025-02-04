from enum import Enum, auto
from dataclasses import dataclass
from sre_constants import CH_LOCALE
from textwrap import dedent
from typing import List, Dict, Optional, Tuple
import datetime
from decimal import Decimal
from loguru import logger
from result import Result, Ok, Err

from src.container import ContainerManager
from src.datatypes import StrategyData
from src.datatypes.trading import PortfolioStatus
from src.db.trading import TradingDB
from src.genner.Base import Genner
from src.sensor.trading import TradingSensor
from src.types import ChatHistory, Message


class TradingPromptGenerator:
	@staticmethod
	def generate_system_prompt(portfolio: str, prev_strat: StrategyData | None) -> str:
		portfolio_str = str(portfolio)
		prev_strat_str = str(prev_strat)

		return dedent(
			"""
			You are a degen speculative tokens trading agent.
			Your ultimate goal is to be richer in 24 hours.
			Here is your current portofolio in ethereum :
			<Portofolio>
			{portfolio_str}
			</Portofolio>
			Yesterday you tried this strategy
			<Strategy>
			{strategy_str}
			</Strategy>
			You can only trade using 1INCH. 
			You will need to research what coins to buy and sell, and write code to do so using the 1INCH API and the ABIs provided.
			""".strip().format(portfolio_str=portfolio_str, strategy_str=prev_strat_str)
		)

	@staticmethod
	def generate_research_code_prompt(portfolio: str) -> str:
		return dedent(
			"""
			You are a degen speculative tokens trading agent, your goal is to be richer in 24 hrs than now. 
			Here is your current portfolio : 
			<Portofolio>
			{portfolio}
			</Portofolio>
			Yesterday you did not trade. 
			You have access to the following APIs: 
			Coingecko (env variables COINGECKO_KEY), 
			Etherscan (env variables ETHERSCAN_KEY), 
			Infura (env variables INFURA_PROJECT_ID),
			Ethereum address and key (env variables ETHER_ADDRESS, ETHER_PRIVATE_KEY),
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
		).format(portfolio=portfolio)

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
			Decide what coin in the ethereum network you should buy today to maximise your chances of making money. You can only trade using 1INCH.
			Reason through your decision process below, formulating a strategy and explaining which coin(s) you will buy.
			""".strip()
		).format(portfolio=portfolio, research=research)

	@staticmethod
	def generate_trading_code_prompt(address_research: str):
		return dedent(
			"""
			You are a crypto trading agent, please generate some code to execute the above strategy.
			Here are some token contract addresses that might help you write the code :
			{address_research}
			You are to generate code in this format below : 
			```python
			from dotenv import load_dotenv
			import ...

			def main():
				....
			
			main()
			```
			You can also use curl to perform swap on 1INCH with our API :
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
		db: TradingDB,
		sensor: TradingSensor,
		genner: Genner,
		container_manager: ContainerManager,
	):
		self.db = db
		self.sensor = sensor
		self.chat_history = ChatHistory()
		self.genner = genner
		self.container_manager = container_manager
		self.strategy = ""

	def reset(self) -> None:
		self.chat_history = ChatHistory()
		self.strategy = ""

	def prepare_system(self, portfolio_data: str, yesterday_strat: StrategyData | None):
		ctx_ch = ChatHistory(
			Message(
				role="system",
				content=TradingPromptGenerator.generate_system_prompt(
					portfolio_data, yesterday_strat
				),
			)
		)

		return ctx_ch

	def gen_market_research_code(
		self, portfolio: str
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=TradingPromptGenerator.generate_research_code_prompt(portfolio),
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

	# def gen_market_research_code_mock(
	# 	self,
	# ) -> Result[Tuple[str, str, ChatHistory], str]:
	# 	code = dedent("""
	# 		```python
	# 		import requests
	# 		import os
	# 		from datetime import datetime

	# 		COINGECKO_API_KEY = os.getenv('COINGECKO_API_KEY', '')  # Optional for basic endpoints
	# 		BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')      # Optional for public data
	# 		CRYPTOCOMPARE_API_KEY = 'CRYPTOCOMPARE_API_KEY'    # Required

	# 		def get_coingecko_btc():
	# 			url = "https://api.coingecko.com/api/v3/simple/price"
	# 			params = {
	# 				"ids": "bitcoin",
	# 				"vs_currencies": "usd",
	# 				"include_market_cap": "true"
	# 			}
	# 			try:
	# 				response = requests.get(url, params=params)
	# 				response.raise_for_status()  # Raise HTTP errors
	# 				data = response.json()
	# 				return {
	# 					"price": data["bitcoin"]["usd"],
	# 					"market_cap": data["bitcoin"]["usd_market_cap"]
	# 				}
	# 			except requests.exceptions.RequestException as e:
	# 				print(f"CoinGecko Error: {e}")
	# 				return None

	# 		def get_binance_orderbook(symbol="BTCUSDT"):
	# 			url = "https://api.binance.com/api/v3/depth"
	# 			params = {"symbol": symbol, "limit": 5}
	# 			try:
	# 				response = requests.get(url, params=params)
	# 				response.raise_for_status()
	# 				data = response.json()
	# 				return {
	# 					"bids": data["bids"][0],  # Top bid
	# 					"asks": data["asks"][0]   # Top ask
	# 				}
	# 			except requests.exceptions.RequestException as e:
	# 				print(f"Binance Error: {e}")
	# 				return None

	# 		def get_cryptocompare_sentiment():
	# 			url = "https://min-api.cryptocompare.com/data/social/coin/latest"
	# 			params = {"coinId": "1182"}  # 1182 = Bitcoin
	# 			headers = {"Apikey": CRYPTOCOMPARE_API_KEY}
	# 			try:
	# 				response = requests.get(url, headers=headers, params=params)
	# 				response.raise_for_status()
	# 				data = response.json()["Data"]
	# 				return {
	# 					"positive": data.get("CryptoCompare", {}).get("Positive", 0),
	# 					"reddit_posts": data.get("Reddit", {}).get("Posts24h", 0)
	# 				}
	# 			except requests.exceptions.RequestException as e:
	# 				print(f"CryptoCompare Error: {e}")
	# 				return None

	# 		if __name__ == "__main__":
	# 			print("Crypto Market Research Dashboard\n" + "-"*30)

	# 			# Fetch data from APIs
	# 			btc_data = get_coingecko_btc()
	# 			orderbook = get_binance_orderbook()
	# 			sentiment = get_cryptocompare_sentiment()

	# 			# Display CoinGecko Data
	# 			if btc_data:
	# 				print(f"\n[CoinGecko] Bitcoin Price: ${btc_data['price']:,.2f}")
	# 				print(f"Market Cap: ${btc_data['market_cap']:,.0f}")

	# 			# Display Binance Order Book
	# 			if orderbook:
	# 				print(f"\n[Binance] BTC/USDT Order Book:")
	# 				print(f"Top Bid: {orderbook['bids'][0]} (Qty: {orderbook['bids'][1]})")
	# 				print(f"Top Ask: {orderbook['asks'][0]} (Qty: {orderbook['asks'][1]})")

	# 			# Display CryptoCompare Sentiment
	# 			if sentiment:
	# 				print(f"\n[CryptoCompare] Social Sentiment:")
	# 				print(f"Positive Sentiment: {sentiment['positive']}%")
	# 				print(f"Reddit Posts (24h): {sentiment['reddit_posts']}")
	# 	""")
	# 	ctx_ch = ChatHistory(
	# 		[
	# 			Message(
	# 				role="user",
	# 				content=TradingPromptGenerator.generate_research_code_prompt(),
	# 			),
	# 			Message(
	# 				role="assistant",
	# 				content=code,
	# 			),
	# 		]
	# 	)

	# 	output = dedent("""
	# 		Crypto Market Research Dashboard
	# 		------------------------------

	# 		[CoinGecko] Bitcoin Price: $45,230.50
	# 		Market Cap: $880,423,105,230

	# 		[Binance] BTC/USDT Order Book:
	# 		Top Bid: 45200.50 (Qty: 1.842)
	# 		Top Ask: 45205.00 (Qty: 2.317)

	# 		[CryptoCompare] Social Sentiment:
	# 		Positive Sentiment: 76%
	# 		Reddit Posts (24h): 2489
	# 	""")

	# 	return Ok((code, output, ctx_ch))

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
