from textwrap import dedent
from typing import List, Tuple
from loguru import logger
from result import Result, Ok, Err

from src.container import ContainerManager
from src.datatypes import StrategyData
from src.genner.Base import Genner
from src.sensor.trading import TradingSensor
from src.types import ChatHistory, Message


from typing import List, Optional, Literal, TypedDict, Dict, Union
from textwrap import dedent
from enum import Enum


class TradingType(Enum):
	SPOT = "spot"
	FUTURES = "futures"
	OPTIONS = "options"


class PositionConfig(TypedDict):
	leverage: Optional[float]  # For futures
	expiry: Optional[str]  # For options
	strike: Optional[float]  # For options
	option_type: Optional[Literal["call", "put"]]  # For options
	side: Literal["long", "short"]


class TradingPromptGenerator:
	@staticmethod
	def _get_trading_specific_instructions(trading_type: TradingType) -> str:
		instructions = {
			TradingType.SPOT: """
            You can trade using 1INCH for spot swaps.
            You will need to research what coins to buy and sell using the 1INCH API.
            """,
			TradingType.FUTURES: """
            You can trade perpetual futures on supported DEXes.
            Key considerations:
            - Leverage and position size
            - Funding rates
            - Liquidation prices
            - Available margin
            """,
			TradingType.OPTIONS: """
            You can trade options on supported DEXes.
            Key considerations:
            - Strike price selection
            - Expiry dates
            - Option Greeks
            - Premium costs
            - Exercise methods
            """,
		}
		return instructions[trading_type]

	@staticmethod
	def _get_api_endpoint_template(trading_type: TradingType) -> str:
		templates = {
			TradingType.SPOT: """
            # Spot trading endpoint
            curl -X POST "http://localhost:9009/api/v1/swap" \\
            -H "Content-Type: application/json" \\
            -d '{
                "token_in": "<token_in_address>",
                "token_out": "<token_out_address>",
                "amount_in": "<amount>",
                "slippage": <slippage>
            }'
            """,
			TradingType.FUTURES: """
            # Futures trading endpoint
            curl -X POST "http://localhost:9009/api/v1/futures" \\
            -H "Content-Type: application/json" \\
            -d '{
                "market": "<market_address>",
                "side": "<long/short>",
                "size": "<position_size>",
                "leverage": "<leverage>",
                "slippage": <slippage>
            }'
            """,
			TradingType.OPTIONS: """
            # Options trading endpoint
            curl -X POST "http://localhost:9009/api/v1/options" \\
            -H "Content-Type: application/json" \\
            -d '{
                "market": "<market_address>",
                "option_type": "<call/put>",
                "strike": "<strike_price>",
                "expiry": "<expiry_timestamp>",
                "size": "<position_size>",
                "slippage": <slippage>
            }'
            """,
		}
		return templates[trading_type]

	@staticmethod
	def generate_system_prompt(
		portfolio: str,
		prev_strat: Optional[StrategyData],
		personality: str,
		trading_type: TradingType,
	) -> str:
		portfolio_str = str(portfolio)
		prev_strat_str = str(prev_strat) if prev_strat else "No previous strategy"
		trading_instructions = (
			TradingPromptGenerator._get_trading_specific_instructions(trading_type)
		)

		return dedent(
			"""
            {personality}
            You are a trader whose ultimate goal is to be richer in 24 hours.
            Here is your current portfolio on Ethereum network:
            <Portfolio>
            {portfolio_str}
            </Portfolio>
            Yesterday you tried this strategy:
            <Strategy>
            {strategy_str}
            </Strategy>
            {trading_instructions}
            """.strip()
		).format(
			personality=personality,
			portfolio_str=portfolio_str,
			strategy_str=prev_strat_str,
			trading_instructions=trading_instructions,
		)

	@staticmethod
	def generate_research_code_prompt(
		portfolio: str, apis: List[str], trading_type: TradingType
	) -> str:
		default_apis = [
			"Coingecko (env variables COINGECKO_KEY)",
			"Etherscan (env variables ETHERSCAN_KEY)",
			"Twitter (env variables TWITTER_API_KEY, TWITTER_API_SECRET)",
			"DuckDuckGo (using the command line `ddgr`)",
		]
		apis_str = ",\n".join(apis if apis else default_apis)
		trading_specific = TradingPromptGenerator._get_trading_specific_instructions(
			trading_type
		)

		return dedent(
			"""
            You are a degen speculative trading agent for {trading_type.value} trading, your goal is to be richer in 24 hrs than now.
            Here is your current portfolio:
            <Portfolio>
            {portfolio}
            </Portfolio>
            Yesterday you did not trade.
            You have access to the following APIs:
            <APIs>
            {apis_str}
            </APIs>
            {trading_specific}
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
		).format(
			portfolio=portfolio,
			apis_str=apis_str,
			trading_type=trading_type,
			trading_specific=trading_specific,
		)

	@staticmethod
	def generate_research_code_on_notif_prompt(
		portfolio: str,
		notification: str,
		apis: List[str],
		strategy: str,
		trading_type: TradingType,
	) -> str:
		default_apis = [
			"Coingecko (env variables COINGECKO_KEY)",
			"Etherscan (env variables ETHERSCAN_KEY)",
			"Twitter (env variables TWITTER_API_KEY, TWITTER_API_SECRET)",
			"DuckDuckGo (using the command line `ddgr`)",
		]
		apis_str = ",\n".join(apis if apis else default_apis)
		trading_specific = TradingPromptGenerator._get_trading_specific_instructions(
			trading_type
		)

		return dedent(
			"""
            You are a degen speculative trading agent for {trading_type.value} trading, your goal is to be richer in 24 hrs than now.
            You have just received a notification:
            <Notification>
            {notification}
            </Notification>
            Bearing in mind your portfolio values:
            <Portfolio>
            {portfolio}
            </Portfolio>
            And access to these API keys:
            <APIs>
            {apis_str}
            </APIs>
            Where this is your current strategy:
            <Strategy>
            {strategy}
            </Strategy>
            {trading_specific}
            Please write code like format below to use your resources to research the state of the market and how to respond.
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
			trading_type=trading_type,
			trading_specific=trading_specific,
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
	def generate_address_research_code_prompt() -> str:
		return dedent(
			"""
            You are a degen speculative tokens trading agent, your goal is to be richer in 24 hrs than now. 
            Above is the result of your market research.
            For the coins mentioned above, please generate some code to get the actual ethereum address of those tokens or the wrapped equivalent.
            Use the Dexscreener API to find the token contract addresses if you do not know them.
            You are to generate like the format below:
            ```python
            from dotenv import load_dotenv
            import ...

            load_dotenv()

            def main():
                ....
            
            main()
            ```
            Please generate the code, and make sure the output are short and concise, you only need to show list of token and its address.
            """
		)

	@staticmethod
	def generate_trading_code_prompt(
		address_research: str,
		trading_type: TradingType,
		position_config: Optional[PositionConfig] = None,
	) -> str:
		api_template = TradingPromptGenerator._get_api_endpoint_template(trading_type)
		trading_specific = TradingPromptGenerator._get_trading_specific_instructions(
			trading_type
		)

		return dedent(
			"""
            You are a crypto trading agent for {trading_type.value} trading, please generate code to execute the strategy.
            Below are the addresses that you can use:
            <Addresses>
            {address_research}
            </Addresses>
            {trading_specific}
            You are to use curl to interact with our API:
            {api_template}
            Write code that implements the strategy using this API.
            Your code must raise an exception if the trade fails so we can detect it.
            Format the code as follows:
            ```python
            from dotenv import load_dotenv
            import ...

            def main():
                ....
            
            main()
            ```
            """.strip()
		).format(
			trading_type=trading_type,
			address_research=address_research,
			trading_specific=trading_specific,
			api_template=api_template,
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
		trading_type: TradingType,
	):
		self.sensor = sensor
		self.chat_history = ChatHistory()
		self.genner = genner
		self.container_manager = container_manager
		self.strategy = ""
		self.trading_type = trading_type

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
					portfolio_data, yesterday_strat, personality, self.trading_type
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
					portfolio, apis, self.trading_type
				),
			)
		)
		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			logger.error(f"TradingAgent.gen_market_research_code, err: \n{err}")
			return Err(f"TradingAgent.gen_market_research_code, err: \n{err}")

		processed_codes, raw_response = gen_result.unwrap()
		logger.info(raw_response)
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_market_research_on_notif_code(
		self, portfolio: str, notification: str, apis: List[str], cur_strat: str
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=TradingPromptGenerator.generate_research_code_on_notif_prompt(
					portfolio, notification, apis, cur_strat, self.trading_type
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
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

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
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

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
		ctx_ch = ctx_ch.append(Message(role="assistant", content=response))

		return Ok((response, ctx_ch))

	def gen_trading_code(
		self, address_research: str
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=TradingPromptGenerator.generate_trading_code_prompt(
					address_research, self.trading_type
				),
			)
		)

		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			logger.error(f"TradingAgent.gen_market_research_code, err: \n{err}")
			return Err(f"TradingAgent.gen_market_research_code, err: \n{err}")

		processed_codes, raw_response = gen_result.unwrap()
		logger.info(raw_response)
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

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
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_strategy_reasoning(self, strategy):
		pass

	def gen_code(self):
		pass

	def gen_code_retry_reasoning(self, output, err):
		pass
