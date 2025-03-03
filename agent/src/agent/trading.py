import re
from textwrap import dedent
from typing import Dict, List, Set, Tuple
from datetime import datetime, timezone, timedelta

from result import Err, Ok, Result

from src.container import ContainerManager
from src.db import APIDB
from src.genner.Base import Genner
from src.client.rag import RAGClient
from src.sensor.trading import TradingSensor
from src.types import ChatHistory, Message


class TradingPromptGenerator:
	def __init__(self, prompts: Dict[str, str]):
		"""
		Initialize with custom prompts for each function.

		Args:
			prompts: Dictionary containing custom prompts for each function
		"""
		if prompts:
			prompts = self.get_default_prompts()
		self._validate_prompts(prompts)
		self.prompts = self.get_default_prompts()

	def _instruments_to_curl_prompt(
		self,
		instruments: List[str],
		txn_service_url: str,
		agent_id: str,
		session_id: str,
	):
		try:
			mapping = {
				# 	"swap_solana": dedent(f"""
				# 	# Swap solana
				# 	curl -X 'POST' \
				# 	'http://{txn_service_url}/api/v1/swap' \
				# 	-H 'accept: application/json' \
				# 	-H 'Content-Type: application/json' \
				# 	-d '{
				# 		"chainId": "<",
				# 		"tokenIn": "string",
				# 		"chainOut": "string",
				# 		"tokenOut": "string",
				# 		"amountIn": "string",
				# 		"slippage": 0.5
				# 	}'
				# """),
				"spot": dedent(f"""
				curl -X POST "http://{txn_service_url}/api/v1/swap" \\
				-H "Content-Type: application/json" \\
				-H "x-superior-agent-id: {agent_id}" \\
				-H "x-superior-session-id: {session_id}" \\
				-d '{{
					"tokenIn": "<token_in_address: str>",
					"tokenOut": "<token_out_address: str>",
					"normalAmountIn": "<amount: str>",
					"slippage": "<slippage: float>"
				}}'
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
			for prompt_name, prompt_content in self.get_default_prompts().items()
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
		self,
		role: str,
		time: str,
		metric_name: str,
		metric_state: str,
		network: str,
	) -> str:
		now = datetime.now()
		today_date = now.strftime("%Y-%m-%d")

		return self.prompts["system_prompt"].format(
			role=role,
			today_date=today_date,
			metric_name=metric_name,
			time=time,
			network=network,
			metric_state=metric_state,
		)

	def generate_research_code_first_time_prompt(self, apis: List[str]):
		apis_str = ",\n".join(apis) if apis else self._get_default_apis_str()

		return self.prompts["research_code_prompt_first"].format(apis_str=apis_str)

	def generate_research_code_prompt(
		self,
		notifications_str: str,
		apis: List[str],
		prev_strategy: str,
		rag_summary: str,
		before_metric_state: str,
		after_metric_state: str,
	):
		apis_str = ",\n".join(apis) if apis else self._get_default_apis_str()

		return self.prompts["research_code_prompt"].format(
			notifications_str=notifications_str,
			apis_str=apis_str,
			prev_strategy=prev_strategy,
			rag_summary=rag_summary,
			before_metric_state=before_metric_state,
			after_metric_state=after_metric_state,
		)

	def generate_strategy_prompt(
		self, notifications_str: str, research_output_str: str, network: str
	) -> str:
		return self.prompts["strategy_prompt"].format(
			notifications_str=notifications_str,
			research_output_str=research_output_str,
			network=network,
		)

	def generate_address_research_code_prompt(
		self,
	) -> str:
		return self.prompts["address_research_code_prompt"].format()

	def generate_trading_code_prompt(
		self,
		strategy_output: str,
		address_research: str,
		apis: List[str],
		trading_instruments: List[str],
		agent_id: str,
		txn_service_url: str,
		session_id: str,
	) -> str:
		trading_instruments_str = self._instruments_to_curl_prompt(
			instruments=trading_instruments,
			agent_id=agent_id,
			txn_service_url=txn_service_url,
			session_id=session_id,
		)

		return self.prompts["trading_code_prompt"].format(
			strategy_output=strategy_output,
			address_research=address_research,
			trading_instruments_str=trading_instruments_str,
		)

	def generate_trading_code_non_address_prompt(
		self,
		strategy_output: str,
		apis: List[str],
		trading_instruments: List[str],
		agent_id: str,
		txn_service_url: str,
		session_id: str,
	):
		trading_instruments_str = self._instruments_to_curl_prompt(
			instruments=trading_instruments,
			agent_id=agent_id,
			txn_service_url=txn_service_url,
			session_id=session_id,
		)
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
			"Coingecko (env variables COINGECKO_API_KEY)",
			"Twitter (env variables TWITTER_API_KEY, TWITTER_API_SECRET)",
			"DuckDuckGo (using the command line `ddgr`)",
		]
		return ",\n".join(default_apis)

	@staticmethod
	def get_default_prompts() -> Dict[str, str]:
		"""Get the complete set of default prompts that can be customized."""
		return {
			"system_prompt": dedent("""
			You are a {role} crypto trader.
			Today's date is {today_date}.
			Your goal is to maximize {metric_name} within {time}
			Your current portfolio on {network} network is: {metric_state}
		""").strip(),
			#
			#
			#
			"research_code_prompt_first": dedent("""
			You know nothing about your environment. 
			Please write code using the format below to research the state of the market.
			You have access to the following APIs:
			<APIs>
			{apis_str}
			</APIs>
			You are to print for everything, and raise every error or unexpected behavior of the program.
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
			#
			#
			"research_code_prompt": dedent("""
			Here is what is going on in your environment right now : 
			<LatestNotification>
			{notifications_str}
			</LatestNotification>
			You have access to these APIs:
			<APIs>
			{apis_str}
			</APIs>
			Your current strategy is: 
			<PrevStrategy>
			{prev_strategy}
			</PrevStrategy>
			For reference, in the past when you encountered a similar situation you reasoned as follows:
			<RAG>
			{rag_summary}
			</RAG>
			The result of this RAG was
			<BeforeStrategyExecution>
			{before_metric_state}
			</BeforeStrategyExecution>
			<AfterStrategyExecution>
			{after_metric_state}
			</AfterStrategyExecution>
			You are to print for everything, and raise every error or unexpected behavior of the program.
			Please write code using format below to research the state of the market and how best to react to it.
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
			#
			#
			"strategy_prompt": dedent("""
			You just learnt the following information: 
			<LatestNotification>
			{notifications_str}
			</LatestNotifications>
			<ResearchOutput>
			{research_output_str}
			</ResearchOutput>
			Decide what coin(s) on the {network} network you should buy today to maximise your chances of making money. 
			Reason through your decision process below, formulating a strategy and explaining which coin(s) you will buy.
		""").strip(),
			#
			#
			#
			"address_research_code_prompt": dedent("""
			Please generate some code to get the address of the tokens mentioned above or the wrapped equivalent.
			Use the Dexscreener API to find the token contract addresses if you do not know them.
			You are to print for everything, and raise every error or unexpected behavior of the program.
			You are to generate code in the the format below:
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
			Please write code to implement the following strategy.
			<Strategy>
			{strategy_output}
			</Strategy>
			Here are some token contract addresses that may help you:
			<AddressResearch>
			{address_research}
			</AddressResearch>
			You are to use curl to interact with our API:
			<TradingInstruments>
			{trading_instruments_str}
			</TradingInstruments>
			You are to comment your code.
			You are to print for everything, and raise every error or unexpected behavior of the program.
			Format the code as follows:
			```python
			from dotenv import load_dotenv
			import ...

			def main():
			....

			main()

			```
			Please generate the code.
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
			You are to print for everything.
			YOU ARE TO RAISE EXCEPTION for every ERRORS, if a data is EMPTY, non 200 response from REQUESTS, and etc. YOU ARE TO RAISE THEM.
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
			You are to print for everything, and raise every error or unexpected behavior of the program.
			You are to generate new code that does not change or stray from the original code.
			You are to generate code that fixes the error, in this format.
			```python
			from dotenv import load_dotenv
			import ...

			load_dotenv()

			def main():
				....
			
			main()
			```
			Please generate the code that fixes the problem..
		""").strip(),
		}


class TradingAgent:
	def __init__(
		self,
		agent_id: str,
		rag: RAGClient,
		db: APIDB,
		sensor: TradingSensor,
		genner: Genner,
		container_manager: ContainerManager,
		prompt_generator: TradingPromptGenerator,
	):
		self.agent_id = agent_id
		self.db = db
		self.rag = rag
		self.sensor = sensor
		self.genner = genner
		self.container_manager = container_manager
		self.prompt_generator = prompt_generator

		self.chat_history = ChatHistory()

	def reset(self) -> None:
		self.chat_history = ChatHistory()

	def prepare_system(
		self, role: str, time: str, metric_name: str, metric_state: str, network: str
	):
		ctx_ch = ChatHistory(
			Message(
				role="system",
				content=self.prompt_generator.generate_system_prompt(
					role=role,
					time=time,
					metric_name=metric_name,
					network=network,
					metric_state=metric_state,
				),
			)
		)

		return ctx_ch

	def gen_research_code_on_first(
		self, apis: List[str]
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_research_code_first_time_prompt(
					apis=apis
				),
			)
		)

		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			return Err(f"TradingAgent.gen_research_code_on_first, err: \n{err}")

		processed_codes, raw_response = gen_result.unwrap()
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_research_code(
		self,
		notifications_str: str,
		apis: List[str],
		prev_strategy: str,
		rag_summary: str,
		before_metric_state: str,
		after_metric_state: str,
	):
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_research_code_prompt(
					notifications_str=notifications_str,
					apis=apis,
					prev_strategy=prev_strategy,
					rag_summary=rag_summary,
					before_metric_state=before_metric_state,
					after_metric_state=after_metric_state,
				),
			)
		)

		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			return Err(f"TradingAgent.gen_research_code, err: \n{err}")

		processed_codes, raw_response = gen_result.unwrap()
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))

	def gen_strategy(
		self,
		notifications_str: str,
		research_output_str: str,
		network: str,
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_strategy_prompt(
					notifications_str=notifications_str,
					research_output_str=research_output_str,
					network=network,
				),
			)
		)

		gen_result = self.genner.ch_completion(self.chat_history + ctx_ch)

		if err := gen_result.err():
			return Err(f"TradingAgent.gen_strategy, err: \n{err}")

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
		agent_id: str,
		txn_service_url: str,
		session_id: str,
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_trading_code_prompt(
					strategy_output=strategy_output,
					address_research=address_research,
					apis=apis,
					trading_instruments=trading_instruments,
					agent_id=agent_id,
					txn_service_url=txn_service_url,
					session_id=session_id,
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
		agent_id: str,
		txn_service_url: str,
		session_id: str,
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_trading_code_non_address_prompt(
					strategy_output=strategy_output,
					apis=apis,
					trading_instruments=trading_instruments,
					agent_id=agent_id,
					txn_service_url=txn_service_url,
					session_id=session_id,
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
