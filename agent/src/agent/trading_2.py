import re
from enum import Enum
from textwrap import dedent
from typing import Dict, List, Literal, Optional, Set, Tuple, TypedDict, Union

from loguru import logger
from result import Err, Ok, Result

from src.container import ContainerManager
from src.datatypes import StrategyData
from src.db import APIDB
from src.genner.Base import Genner
from src.sensor.trading import TradingSensor
from src.types import ChatHistory, Message


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

	@staticmethod
	def _instruments_to_curl_prompt(instruments: List[str]):
		try:
			mapping = {
				"spot": dedent("""
				# Spot 
				curl -X POST "http://localhost:9009/api/v1/swap" \\
				-H "Content-Type: application/json" \\
				-d '{
					"token_in": "<token_in_address>",
					"token_out": "<token_out_address>",
					"amount_in": "<amount>",
					"slippage": "<slippage>"
				}'
			"""),
				"futures": dedent("""
				# Futures
				curl -X POST "http://localhost:9009/api/v1/futures/position" \\
				-H "Content-Type: application/json" \\
				-d '{
					"market": "<market_symbol>",
					"side": "<long|short>",
					"leverage": "<leverage_multiplier>",
					"size": "<position_size>",
					"stop_loss": "<optional_stop_loss_price>",
					"take_profit": "<optional_take_profit_price>"
				}'
			"""),
				"options": dedent("""
				# Options
				curl -X POST "http://localhost:9009/api/v1/options/trade" \\
				-H "Content-Type: application/json" \\
				-d '{
					"underlying": "<asset_symbol>",
					"option_type": "<call|put>",
					"strike_price": "<strike_price>",
					"expiry": "<expiry_timestamp>",
					"amount": "<contracts_amount>",
					"side": "<buy|sell>"
				}'
			"""),
				"defi": dedent("""
				# Defi
				curl -X POST "http://localhost:9009/api/v1/defi/interact" \\
				-H "Content-Type: application/json" \\
				-d '{
					"protocol": "<protocol_name>",
					"action": "<deposit|withdraw|stake|unstake>",
					"asset": "<asset_address>",
					"amount": "<amount>",
					"pool_id": "<optional_pool_id>",
					"slippage": "<slippage_tolerance>"
				}'
			"""),
			}
			instruments_str = [mapping[instrument] for instrument in instruments]
			return "\n".join(instruments_str)
		except KeyError as e:
			raise KeyError(
				f"Expected trading_instruments to be in ['spot', 'defi', 'futures', 'options'], {e}"
			)

	@staticmethod
	def _metric_to_metric_prompt(metric_name="wallet"):
		try:
			mapping = {"wallet": "your money in a crypto wallet"}

			return mapping[metric_name]
		except KeyError as e:
			raise KeyError(f"Expected to metric_name to be in ['wallet'], {e}")

	def _extract_default_placeholders(self) -> Dict[str, Set[str]]:
		"""Extract placeholders from default prompts to use as required placeholders."""
		placeholder_pattern = re.compile(r"{([^}]+)}")
		return {
			prompt_name: {
				f"{{{p}}}" for p in placeholder_pattern.findall(prompt_content)
			}
			for prompt_name, prompt_content in self.get_default_prompts.items()
		}

	def _validate_prompts(self, prompts: Dict[str, str]) -> None:
		"""
		Validate prompts for required and unexpected placeholders.

		Args:
			prompts: Dictionary of prompt name to prompt content

		Raises:
			ValueError: If prompts are missing required placeholders or contain unexpected ones
		"""
		required_placeholders = self._extract_default_placeholders()

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
		self, role: str, time: str, metric_name: str, metric_state: str
	) -> str:
		return self.prompts["system_prompt"].format(
			role=role, time=time, metric_name=metric_name, metric_state=metric_state
		)

	def generate_strategy_first_time_prompt(self, apis: List[str]):
		apis_str = ",\n".join(apis) if apis else self._get_default_apis_str()

		return self.prompts["strategy_prompt_first"].format(apis_str=apis_str)

	def generate_strategy_prompt(
		self,
		cur_environment: str,
		prev_strategy: str,
		prev_strategy_result: str,
		apis: List[str],
	) -> str:
		apis_str = ",\n".join(apis) if apis else self._get_default_apis_str()

		return self.prompts["strategy_prompt"].format(
			cur_environment=cur_environment,
			prev_strategy=prev_strategy,
			prev_strategy_result=prev_strategy_result,
			apis_str=apis_str,
		)

	def generate_address_research_code_prompt(self) -> str:
		return self.prompts["address_research_code_prompt"]

	def generate_trading_code_prompt(
		self,
		strategy_output: str,
		address_research: str,
		apis: List[str],
		trading_instruments: List[str],
	) -> str:
		trading_instruments_str = self._instruments_to_curl_prompt(trading_instruments)
		apis_str = ",\n".join(apis) if apis else self._get_default_apis_str()
		apis_str += "\n"
		apis_str += trading_instruments_str

		return self.prompts["trading_code_prompt"].format(
			strategy_output=strategy_output,
			address_research=address_research,
			apis_str=apis_str,
			trading_instruments_str=trading_instruments_str,
		)

	def generate_trading_code_non_address_prompt(
		self,
		strategy_output: str,
		apis: List[str],
		trading_instruments: List[str],
	):
		trading_instruments_str = self._instruments_to_curl_prompt(trading_instruments)
		apis_str = ",\n".join(apis) if apis else self._get_default_apis_str()
		apis_str += "\n"
		apis_str += trading_instruments_str

		return self.prompts["trading_code_non_address_prompt"].format(
			strategy_output=strategy_output,
			apis_str=apis_str,
			trading_instruments_str=trading_instruments_str,
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
			You are a {role} crypto trader
			Your goal is to maximize {metric_name} within {time}
			You are currently at {metric_state}
		""").strip(),
			#
			#
			#
			"strategy_prompt_first": dedent("""
			You know nothing about your environment.
			What do you do now?
			You can use the following API to do research or run code to interact with the worlds :
			<APIs>
			{apis_str}
			</APIs>
			Please explain your approach.
		""").strip(),
			#
			#
			#
			"strategy_prompt": dedent("""
			Here is what is going on in your environment right now :{cur_environment}.
			Here is what you just tried :{prev_strategy}.
			It {prev_strategy_result}.
			What do you do now?
			You can pursue or modify your current approach or try a new one.
			You can use the following APIs to do further research or run code to interact with the world :
			<APIs>
			{apis_str}
			</APIs>
			Please explain your approach.
		""").strip(),
			#
			#
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
			#
			#
			"trading_code_prompt": dedent("""
			Please write code to implement this strategy : 
			<Strategy>
			{strategy_output}
			</Strategy>
			You have the following APIs : 
			<APIs>
			{apis_str}
			</APIs>
			You may use the information on these contract addresses :
			<AddressResearch>
			{address_research}
			</AddressResearch>
			And you may use these local service as trading instruments to perform your task:
			<TradingInstruments>
			{trading_instruments_str}
			</TradingInstruments>
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
			#
			#
			"trading_code_non_address_prompt": dedent("""
			Please write code to implement this strategy : 
			<Strategy>
			{strategy_output}
			</Strategy>
			You have the following APIs : 
			<APIs>
			{apis_str}
			</APIs>
			And you may use these local service as trading instruments to perform your task:
			<TradingInstruments>
			{trading_instruments_str}
			</TradingInstruments>
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
			#
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
		id: str,
		sensor: TradingSensor,
		genner: Genner,
		container_manager: ContainerManager,
		prompt_generator: TradingPromptGenerator,
		db: APIDB,
	):
		self.id = id
		self.sensor = sensor
		self.chat_history = ChatHistory()
		self.genner = genner
		self.container_manager = container_manager
		self.db = db
		self.prompt_generator = prompt_generator

	def reset(self) -> None:
		self.chat_history = ChatHistory()

	def prepare_system(self, role: str, time: str, metric_name: str, metric_state: str):
		ctx_ch = ChatHistory(
			Message(
				role="system",
				content=self.prompt_generator.generate_system_prompt(
					role=role, time=time, metric_name=metric_name, metric_state=metric_state
				),
			)
		)

		return ctx_ch

	def gen_strategy(
		self,
		cur_environment: str,
		prev_strategy: str,
		prev_strategy_result: str,
		apis: List[str],
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_strategy_prompt(
					cur_environment=cur_environment,
					prev_strategy=prev_strategy,
					prev_strategy_result=prev_strategy_result,
					apis=apis,
				),
			)
		)

		gen_result = self.genner.ch_completion(self.chat_history + ctx_ch)

		if err := gen_result.err():
			return Err(f"TradingAgent.gen_strategy, err: \n{err}")

		response = gen_result.unwrap()
		ctx_ch = ctx_ch.append(Message(role="assistant", content=response))

		return Ok((response, ctx_ch))

	def gen_strategy_on_first(
		self, apis: List[str]
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_strategy_first_time_prompt(
					apis=apis
				),
			)
		)

		gen_result = self.genner.ch_completion(self.chat_history + ctx_ch)

		if err := gen_result.err():
			return Err(f"TradingAgent.gen_strategy_on_first, err: \n{err}")

		response = gen_result.unwrap()
		ctx_ch = ctx_ch.append(Message(role="assistant", content=response))

		return Ok((response, ctx_ch))

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
			return Err(f"TradingAgent.gen_account_research_code, err: \n{err}")

		processed_codes, raw_response = gen_result.unwrap()
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_trading_code(
		self,
		strategy_output: str,
		address_research: str,
		apis: List[str],
		trading_instruments: List[str],
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_trading_code_prompt(
					strategy_output=strategy_output,
					address_research=address_research,
					apis=apis,
					trading_instruments=trading_instruments,
				),
			)
		)

		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			return Err(f"TradingAgent.gen_trading_code, err: \n{err}")

		processed_codes, raw_response = gen_result.unwrap()
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_trading_non_address_code(
		self,
		strategy_output: str,
		apis: List[str],
		trading_instruments: List[str],
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_trading_code_non_address_prompt(
					strategy_output=strategy_output,
					apis=apis,
					trading_instruments=trading_instruments,
				),
			)
		)

		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			return Err(f"TradingAgent.gen_trading_non_address_code, err: \n{err}")

		processed_codes, raw_response = gen_result.unwrap()
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
			return Err(f"TradingAgent.gen_better_code, err: \n{err}")

		processed_codes, raw_response = gen_result.unwrap()
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))
