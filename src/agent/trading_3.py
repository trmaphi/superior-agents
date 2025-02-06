import re
from enum import Enum
from textwrap import dedent
from typing import Dict, List, Literal, Optional, Tuple, TypedDict, Union

from loguru import logger
from result import Err, Ok, Result

from src.container import ContainerManager
from src.datatypes import StrategyData
from src.genner.Base import Genner
from src.sensor.trading import TradingSensor
from src.types import ChatHistory, Message


class TradingType(Enum):
	SPOT = "spot"
	FUTURES = "futures"
	OPTIONS = "options"


class TradingPromptGenerator:
	def __init__(self, prompts: Dict[str, str]):
		"""
		Initialize with custom prompts for each function.

		Args:
			prompts: Dictionary containing custom prompts for each function
			trading_type: Type of trading being performed

		Required prompt keys:
		- system_prompt
		- research_code_prompt
		- research_code_on_notif_prompt
		- strategy_prompt
		- address_research_code_prompt
		- trading_code_prompt
		- regen_code_prompt
		"""
		if prompts:
			prompts = self.get_default_prompts()
		self._validate_prompts(prompts)
		self.prompts = self.get_default_prompts()

	def _validate_prompts(self, prompts: Dict[str, str]) -> None:
		"""
		Validate prompts for required and unexpected placeholders.

		Args:
			prompts: Dictionary of prompt name to prompt content

		Raises:
			ValueError: If prompts are missing required placeholders or contain unexpected ones
		"""
		required_placeholders = {
			"system_prompt": {
				"{personality}",
				"{portfolio_str}",
				"{strategy_str}",
				"{trading_instructions}",
			},
			"research_code_prompt": {
				"{portfolio}",
				"{apis_str}",
				"{trading_type}",
				"{trading_specific}",
			},
			"research_code_on_notif_prompt": {
				"{notification}",
				"{portfolio}",
				"{apis_str}",
				"{strategy}",
				"{trading_type}",
				"{trading_specific}",
			},
			"strategy_prompt": {"{portfolio}", "{research}"},
			"address_research_code_prompt": {"{market_research}"},
			"trading_code_prompt": {
				"{address_research}",
				"{trading_type}",
				"{trading_specific}",
				"{api_template}",
			},
			"regen_code_prompt": {"{errors}", "{previous_code}"},
		}

		# Check all required prompts exist
		missing_prompts = set(required_placeholders.keys()) - set(prompts.keys())
		if missing_prompts:
			raise ValueError(f"Missing required prompts: {missing_prompts}")

		# Extract placeholders using regex
		placeholder_pattern = re.compile(r"{([^}]+)}")

		# Check each prompt for missing and unexpected placeholders
		for prompt_name, prompt_content in prompts.items():
			if prompt_name not in required_placeholders:
				continue

			# Get actual placeholders in the prompt
			actual_placeholders = {
				f"{{{p}}}" for p in placeholder_pattern.findall(prompt_content)
			}
			required_set = required_placeholders[prompt_name]

			# Check for missing placeholders
			missing = required_set - actual_placeholders
			if missing:
				raise ValueError(
					f"Missing required placeholders in {prompt_name}: {missing}"
				)

			# Check for unexpected placeholders
			unexpected = actual_placeholders - required_set
			if unexpected:
				raise ValueError(
					f"Unexpected placeholders in {prompt_name}: {unexpected}"
				)

	def generate_system_prompt(
		self,
		portfolio: str,
		prev_strat: Optional[StrategyData],
		personality: str,
	) -> str:
		portfolio_str = str(portfolio)
		prev_strat_str = str(prev_strat) if prev_strat else "No previous strategy"

		return self.prompts["system_prompt"].format(
			personality=personality,
			portfolio_str=portfolio_str,
			strategy_str=prev_strat_str,
		)

	def generate_research_code_prompt(self, portfolio: str, apis: List[str]) -> str:
		apis_str = ",\n".join(apis) if apis else self._get_default_apis_str()

		return self.prompts["research_code_prompt"].format(
			portfolio=portfolio, apis_str=apis_str
		)

	def generate_research_code_on_notif_prompt(
		self,
		portfolio: str,
		notification: str,
		apis: List[str],
		strategy: str,
	) -> str:
		apis_str = ",\n".join(apis) if apis else self._get_default_apis_str()

		return self.prompts["research_code_on_notif_prompt"].format(
			portfolio=portfolio,
			notification=notification,
			apis_str=apis_str,
			strategy=strategy,
		)

	def generate_strategy_prompt(self, portfolio: str, research: str) -> str:
		return self.prompts["strategy_prompt"].format(
			portfolio=portfolio, research=research
		)

	def generate_address_research_code_prompt(self) -> str:
		return self.prompts["address_research_code_prompt"]

	def generate_trading_code_prompt(
		self,
		address_research: str,
	) -> str:
		return self.prompts["trading_code_prompt"].format(
			address_research=address_research
		)

	def regen_code(self, previous_code: str, errors: str) -> str:
		return self.prompts["regen_code_prompt"].format(
			errors=errors, previous_code=previous_code
		)

	@staticmethod
	def _get_default_apis_str() -> str:
		default_apis = [
			"Coingecko (env variables COINGECKO_KEY)",
			"Etherscan (env variables ETHERSCAN_KEY)",
			"Twitter (env variables TWITTER_API_KEY, TWITTER_API_SECRET)",
			"DuckDuckGo (using the command line `ddgr`)",
		]
		return ",\n".join(default_apis)

	@staticmethod
	def get_default_prompts() -> Dict[str, str]:
		"""Get the complete set of default prompts that can be customized."""
		return {
			"system_prompt": dedent("""
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
		""").strip(),
			#
			"research_code_prompt": dedent("""
			You are a degen speculative trading agent, your goal is to be richer in 24 hrs than now.
			Here is your current portfolio:
			<Portfolio>
			{portfolio}
			</Portfolio>
			Yesterday you did not trade.
			You have access to the following APIs:
			<APIs>
			{apis_str}
			</APIs>
			Please write code like format below to use your resources to research the state of the market.
			```python
			from dotenv import load_dotenv
			import ...

			load_dotenv()

			def main():
				....
			
			main()
			```
		""").strip(),
			#
			"research_code_on_notif_prompt": dedent("""
			You are a degen speculative trading agent, your goal is to be richer in 24 hrs than now.
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
			Please write code like format below to use your resources to research the state of the market and how to respond.
			```python
			from dotenv import load_dotenv
			import ...

			load_dotenv()

			def main():
				....
			
			main()
			```
		""").strip(),
			#
			"strategy_prompt": dedent("""
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
		""").strip(),
			#
			"address_research_code_prompt": dedent("""
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
		""").strip(),
			#
			"trading_code_prompt": dedent("""
			You are a crypto trading agent, please generate code to execute the strategy.
			Below are the addresses that you can use:
			<Addresses>
			{address_research}
			</Addresses>
			You are to use curl to interact with our API:
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
		""").strip(),
			#
			"regen_code_prompt": dedent("""
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
		""").strip(),
		}


class TradingAgent:
	def __init__(
		self,
		sensor: TradingSensor,
		genner: Genner,
		container_manager: ContainerManager,
		prompt_generator: TradingPromptGenerator,
	):
		self.sensor = sensor
		self.chat_history = ChatHistory()
		self.genner = genner
		self.container_manager = container_manager
		self.strategy = ""
		self.prompt_generator = prompt_generator

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
				content=self.prompt_generator.generate_system_prompt(
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
				content=self.prompt_generator.generate_research_code_prompt(
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
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_market_research_on_notif_code(
		self, portfolio: str, notification: str, apis: List[str], cur_strat: str
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_research_code_on_notif_prompt(
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
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_account_research_code(
		self,
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_address_research_code_prompt(),
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
				content=self.prompt_generator.generate_strategy_prompt(
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
				content=self.prompt_generator.generate_trading_code_prompt(
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
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_better_code(
		self, prev_code: str, errors: str
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.regen_code(prev_code, errors),
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
