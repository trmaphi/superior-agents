import re
from textwrap import dedent
from typing import Dict, List, Optional, Set, Tuple

from result import Err, Ok, Result

from src.container import ContainerManager
from src.datatypes import StrategyData
from src.datatypes.marketing import NewsData
from src.db import APIDB
from src.db.marketing import MarketingDB
from src.genner.Base import Genner
from src.sensor.marketing import MarketingSensor
from src.twitter import TweetData
from src.types import ChatHistory, Message


class MarketingPromptGenerator:
	def __init__(self, prompts: Optional[Dict[str, str]] = None):
		"""
		Initialize with custom prompts for each function.

		Args:
			prompts: Dictionary containing custom prompts for each function
		"""
		if prompts is None:
			prompts = self.get_default_prompts()
		self._validate_prompts(prompts)
		self.prompts = prompts

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

	def generate_strategy_first_time_prompt(self, apis: List[str]) -> str:
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

	def generate_marketing_code_prompt(
		self, strategy_output: str, apis: List[str]
	) -> str:
		"""Generate prompt for implementing the strategy"""
		apis_str = ",\n".join(apis) if apis else self._get_default_apis_str()
		return self.prompts["trading_code_prompt"].format(
			strategy_output=strategy_output, apis_str=apis_str
		)

	def regen_code(self, previous_code: str, errors: str) -> str:
		"""Generate prompt for fixing code errors"""
		return self.prompts["regen_code_prompt"].format(
			errors=errors, previous_code=previous_code
		)

	@staticmethod
	def _get_default_apis_str() -> str:
		"""Get default list of available APIs"""
		default_apis = [
			"Twitter API v2 (env variables TWITTER_API_KEY, TWITTER_API_SECRET)",
			"Twitter API v1.1 (for legacy endpoints)",
			"DuckDuckGo (using the command line `ddgr`)",
		]
		return ",\n".join(default_apis)

	@staticmethod
	def get_default_prompts() -> Dict[str, str]:
		"""Get the complete set of default prompts that can be customized."""
		return {
			"system_prompt": dedent("""
				You are a {role}.
				You are also a social media influencer.
				Your goal is to maximize {metric_name} within {time}
				You are currently at {metric_state}
			""").strip(),
			#
			#
			#
			"strategy_prompt_first": dedent("""
				You know nothing about your environment.
				What do you do now?
				You can use the following APIs to do research or run code to interact with the world:
				<APIs>
				{apis_str}
				</APIs>
				Please explain your approach.
			""").strip(),
			#
			#
			#
			"strategy_prompt": dedent("""
				Here is what is going on in your environment right now: {cur_environment}
				Here is what you just tried: {prev_strategy}
				It {prev_strategy_result}
				What do you do now?
				You can pursue or modify your current approach or try a new one.
				You can use the following APIs to do further research or run code to interact with the world:
				<APIs>
				{apis_str}
				</APIs>
				Please explain your approach.
			""").strip(),
			#
			#
			#
			"marketing_code_prompt": dedent("""
				Please write code to implement this strategy:
				<Strategy>
				{strategy_output}
				</Strategy>
				You have the following APIs:
				<APIs>
				{apis_str}
				</APIs>
				Format the code as follows:
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
			"regen_code_prompt": dedent("""
				Given these errors:
				<Errors>
				{errors}
				</Errors>
				And the code it's from:
				<Code>
				{previous_code}
				</Code>
				You are to generate code that fixes the error but doesn't stray too much from the original code, in this format:
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


class MarketingAgent:
	def __init__(
		self,
		id: str,
		db: APIDB,
		sensor: MarketingSensor,
		genner: Genner,
		container_manager: ContainerManager,
		prompt_generator: MarketingPromptGenerator,
	):
		self.id = id
		self.db = db
		self.sensor = sensor
		self.chat_history = ChatHistory()
		self.genner = genner
		self.container_manager = container_manager
		self.prompt_generator = prompt_generator
		self.strategy = ""

	def reset(self) -> None:
		self.chat_history = ChatHistory()
		self.strategy = ""

	def prepare_system(self, role: str, time: str, metric_name: str, metric_state: str):
		ctx_ch = ChatHistory(
			Message(
				role="system",
				content=self.prompt_generator.generate_system_prompt(
					role=role, time=time,metric_name=metric_name, metric_state=metric_state
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
			return Err(f"MarketingAgent.gen_strategy, err: \n{err}")

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
			return Err(f"MarketingAgent.gen_strategy_on_first, err: \n{err}")

		response = gen_result.unwrap()
		ctx_ch = ctx_ch.append(Message(role="assistant", content=response))

		return Ok((response, ctx_ch))

	def gen_marketing_code(
		self,
		strategy_output: str,
		apis: List[str],
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_marketing_code_prompt(
					strategy_output=strategy_output,
					apis=apis,
				),
			)
		)

		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			return Err(f"MarketingAgent.gen_trading_code, err: \n{err}")

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
			return Err(
				f"MarketingAgent.gen_better_code, failed on regenerating code, err: \n{err}"
			)

		processed_codes, raw_response = gen_result.unwrap()
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))
