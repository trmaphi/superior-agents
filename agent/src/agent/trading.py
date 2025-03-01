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
					"token_in": "<token_in_address>",
					"token_out": "<token_out_address>",
					"amount_in": "<amount>",
					"slippage": "<slippage>"
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
			time=time,
			metric_name=metric_name,
			network=network,
			metric_state=metric_state,
		)

	def generate_research_code_first_time_prompt(self, apis: List[str]):
		apis_str = ",\n".join(apis) if apis else self._get_default_apis_str()

		return self.prompts["research_code_prompt_first"].format(apis_str=apis_str)

	def generate_research_code_prompt(
		self,
		prev_strategy: str,
		summarized_prev_code: str,
		prev_code_output: str,
		apis: List[str],
	):
		apis_str = ",\n".join(apis) if apis else self._get_default_apis_str()

		return self.prompts["research_code_prompt"].format(
			prev_strategy=prev_strategy,
			summarized_prev_code=summarized_prev_code,
			prev_code_output=prev_code_output,
			apis_str=apis_str,
		)

	def generate_strategy_prompt(
		self,
		notifications_str: str,
		research_output_str: str,
		prev_strategy: str,
		summarized_prev_code: str,
		prev_code_output: str,
		rag_summary: str,
		before_metric_state: str,
		after_metric_state: str,
		apis: List[str],
	) -> str:
		apis_str = ",\n".join(apis) if apis else self._get_default_apis_str()

		return self.prompts["strategy_prompt"].format(
			notifications_str=notifications_str,
			research_output_str=research_output_str,
			prev_strategy=prev_strategy,
			summarized_prev_code=summarized_prev_code,
			prev_code_output=prev_code_output,
			rag_summary=rag_summary,
			before_metric_state=before_metric_state,
			after_metric_state=after_metric_state,
			apis_str=apis_str,
		)

	def generate_address_research_code_prompt(
		self,
		role: str,
		time: str,
		metric_name: str,
		metric_state: str,
		strategy_output: str,
	) -> str:
		return self.prompts["address_research_code_prompt"].format(
			role=role,
			time=time,
			metric_name=metric_name,
			metric_state=metric_state,
			strategy_output=strategy_output,
		)

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
			#
			#
			#
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
			You can use the following APIs to do research and learn more:
			<APIs>
			{apis_str}
			</APIs>
			Please write code to learn something that will help you fulfill your goals.
			You are encouraged to research and find the states of as many assets as possible.
			You are also to make sure that you are printing every steps in the code.
			You are to print every information you managed to get.
			You are to not bother try/catching the error, its better to just crash the program if something unexpected happens
			You are to generate the code like the format to maximize your metric below:
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
			#
			#
			#
			"research_code_prompt": dedent("""
			In the last cycle you tried the following apporach: 
			<PrevStrategy>
			{prev_strategy}
			</PrevStrategy>
			And here's the summarized code:
			<SummarizedCode>
			{summarized_prev_code}
			</SummarizedCode>
			And it's final output was :
			<CodeOutput>
			{prev_code_output}
			</CodeOutput>
			Please use the following APIs to do research and work out how to improve on this in the next cycle:
			<APIs>
			{apis_str}
			</APIs>
			Please write code to learn something that will help you fulfill your goals.
			You are encouraged to research and find the state as many assets as possible.
			You are also to make sure you are printing every steps you're taking in the code for the original code.
			Account for everything, and for every failure of the steps, you are to raise exceptions.
			Dont bother try/catching the error, its better to just crash the program if something unexpected happens
			You are to print every information you managed to get.
			You are also to crash if the result of anything you are doing is empty.
			You are to generate like the format below:
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
			#
			#
			#
			"strategy_prompt": dedent("""
			Here is what is going on in your environment right now : 
			<Notifications>
			{notifications_str}
			</Notifications>
			<Research>
			{research_output_str}
			</Research>
			In the last cycle you tried the following apporach: 
			<PrevStrategy>
			{prev_strategy}
			</PrevStrategy>
			And here's the summarized code :
			<SummarizedCode>
			{summarized_prev_code}
			</SummarizedCode>
			And it's final output was :
			<CodeOutput>
			{prev_code_output}
			</CodeOutput>
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
			To help you, you have access to the following APIs :
			<APIs>
			{apis_str}
			</APIs>
			What do you want to do? 
			Reason through your decision process below, formulating a strategy and explaining which assets(s) you want to act with.
			For now just generate a strategy and dont generate code.
		""").strip(),
			#
			#
			#
			"address_research_code_prompt": dedent("""
			You are a {role} crypto trader
			Your goal is to maximize {metric_name} within {time}
			You are currently at {metric_state}
			This is your strategy
			<Strategy>
			{strategy_output}
			</Strategy>
			For the coins mentioned above, please generate some code to get the actual address of those tokens or the wrapped equivalent.
			Use the DexScreener (Free API (GET https://api.dexscreener.com/token-profiles/latest/v1)) to find the token contract addresses if you do not know them.
			The DexScreener API returns ({{"url":"","chainId":"","tokenAddress":"","icon":"","header":"","description":"text","links":[{{"type":"","label":"","url":""}}]}})
			You are to print the addresses in short and consise way that the output can be used in your next reply.
			Dont bother try/catching the error, its better to just crash the program if something unexpected happens.
			You are also to crash if the result of anything you are doing is empty.
			You are to print every information you managed to get.
			You are to generate like the format below:
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
			#
			#
			#
			"trading_code_prompt": dedent("""
			Please write code to implement this strategy and ONLY this strategy: 
			<Strategy>
			{strategy_output}
			</Strategy>
			You have the following APIs : 
			<APIs>
			{apis_str}
			</APIs>
			Here are some token contract addresses that may help you:
			<AddressResearch>
			{address_research}
			</AddressResearch>
			If - BUT ONLY IF - your strategy requires you to make any trades, you may use these local services:
			<TradingInstruments>
			{trading_instruments_str}
			</TradingInstruments>
			Comment your code.
			Account for everything, for every failure raise exceptions.
			Dont bother try/catching the errors, its better to just crash the program if something unexpected happens
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
		prev_strategy: str,
		summarized_prev_code: str,
		prev_code_output: str,
		apis: List[str],
	):
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_research_code_prompt(
					prev_strategy=prev_strategy,
					summarized_prev_code=summarized_prev_code,
					prev_code_output=prev_code_output,
					apis=apis,
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
		prev_strategy: str,
		summarized_prev_code: str,
		prev_code_output: str,
		apis: List[str],
		rag_summary: str,
		before_metric_state: str,
		after_metric_state: str,
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_strategy_prompt(
					notifications_str=notifications_str,
					research_output_str=research_output_str,
					prev_strategy=prev_strategy,
					summarized_prev_code=summarized_prev_code,
					prev_code_output=prev_code_output,
					apis=apis,
					rag_summary=rag_summary,
					before_metric_state=before_metric_state,
					after_metric_state=after_metric_state,
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
		role: str,
		time: str,
		metric_name: str,
		metric_state: str,
		strategy_output: str,
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_address_research_code_prompt(
					role=role,
					time=time,
					metric_name=metric_name,
					metric_state=metric_state,
					strategy_output=strategy_output,
				),
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
