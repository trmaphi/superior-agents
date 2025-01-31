from textwrap import dedent
from typing import List, Tuple

from loguru import logger
from result import Err, Ok, Result
from src.container import ContainerManager
from src.db import DB
from src.genner.Base import Genner
from src.sensor import AgentSensor
from src.twitter import TweetData
from src.types import ChatHistory, Message, StrategyData


class TwitterPromptGenerator:
	@staticmethod
	def generate_system_prompt(
		followers_count: int, follower_tweets: List[TweetData]
	) -> str:
		formatted_tweets = []

		for tweet in follower_tweets:
			tweet_yaml = dedent(f"""
				-   id: "{tweet.id}"
					text: "{tweet.text}"
					created_at: "{tweet.created_at}"
					author_id: "{tweet.author_id}"
					author_username: "{tweet.author_username}"
					thread_id: "{tweet.thread_id}"
			""").strip()
			formatted_tweets.append(tweet_yaml)

		follower_tweets_str = "\n".join(formatted_tweets)

		return dedent(
			"""
			You are a marketing agent in twitter/X.
			You have {followers_count} followers.
			Your goal is to maximize the number of followers you have.
			You are tasked with generating strategies, reasoning, and code to achieve this.
			You are also assisted by these sampled follower tweets:
			<FollowerTweets>
			```yaml
			{follower_tweets}
			```
			</FollowerTweets>
			""".strip()
		).format(followers_count=followers_count, follower_tweets=follower_tweets_str)

	@staticmethod
	def generate_strategy_prompt(prev_strats: List[StrategyData]) -> str:
		formatted_strats = []
		for strat in prev_strats:
			strat_yaml = dedent(f"""
				-   idx: "{strat.idx}"
					strategy: "{strat.name}"
					result: "{strat.strategy_result}"
					reasoning: |
						{strat.reasoning}
					ran_at: "{strat.ran_at}"
			""").strip()
			formatted_strats.append(strat_yaml)
		prev_strats_str = "\n".join(formatted_strats)

		return dedent(
			"""
			You are a marketing agent in twitter/X.
			This is the previous strats that you have generated, and it's results:
			<PrevStrats>
			```yaml
			{prev_strats}
			```
			</PrevStrats>
			Generate some new strategies that might perform better than those that you have generated, or the same if you think it's good enough.
			You are to put them in yaml format. Like this:
			```yaml
			- "Strategy 1"
			- "Strategy 2"
			...
			- "Strategy N"
			```
			""".strip()
		).format(prev_strats=prev_strats_str)

	@staticmethod
	def generate_post_strategy_reasoning_prompt(strategy: StrategyData) -> str:
		formatted_strategy = dedent(f"""
			-   idx: "{strategy.idx}"
				strategy: "{strategy.name}"
				result: "{strategy.strategy_result}"
				reasoning: |
					{strategy.reasoning}
				ran_at: "{strategy.ran_at}"
		""").strip()

		return dedent(
			"""
			You are a marketing agent in twitter/X.
			This is the strategy that you are going to use:
			<Strategy>
			{strategy}
			</Strategy>
			You are to generate reasonings on why you think this strategy will work.
			You are to generate 2 types of reasoning, reasoning of success and reasoning of failure.
			You are to put them in xml format. Like these:
			<ReasonsToSuccess>
			```yaml
			- "Reason to success 1"
			- "Reason to success 2"
			...
			- "Reason to success N"
			```
			</ReasonsToSuccess>
			<ReasonsToFail>
			```yaml
			- "Reason to fail 1"
			- "Reason to fail 2"
			...
			- "Reason to fail N"
			```
			</ReasonsToFail>
			""".strip()
		).format(strategy=formatted_strategy)

	@staticmethod
	def generate_code_prompt() -> str:
		return dedent(
			"""
			You are a marketing agent in twitter/X.
			Above is your reasoning on why you think the strategy will work and why it will not.
			Generate code from the reasonings that you have generated.
			You are to use private keys using the library `dotenv` and use those environment variables to authenticate with the Twitter API.
			These are the list of the environment variables provided by the `dotenv`: [
				"API_KEY",
				"API_SECRET",
				"BEARER_TOKEN",
				"ACCESS_TOKEN",
				"ACCESS_TOKEN_SECRET",
			]
			You are to use tweepy or direct twitter HTTP api to execute your strategy.
			You are to put them in python format. Like this:
			```python
			from dotenv import load_dotenv
			import os
			from tweepy import ...

			load_dotenv()
			def my_strategy():
				# os.getenv(...)
				# Code here
				pass

			if __name__ == "__main__":
				my_strategy()
			```
			""".strip()
		)

	@staticmethod
	def generate_post_code_reasoning_prompt(
		errors: str | None, outputs: str | None
	) -> str:
		assert errors != ""
		assert outputs != ""

		fail_sub_prompt = (
			dedent("""
			<Errors>
			{errors}
			</Errors>
		""")
			.strip()
			.format(errors=errors if errors is not None else "")
		)

		success_sub_prompt = (
			dedent("""
			<Outputs>
			{outputs}
			</Outputs>
		""")
			.strip()
			.format(outputs=outputs if outputs is not None else "")
		)

		result_str = fail_sub_prompt if errors is not None else success_sub_prompt

		return dedent(
			"""
			You are a marketing agent in twitter/X.
			You have replied a code before, and and in this string is the result of the execution.
			Generate reasoning as of why the result is as such.
			If it's tagged <Errors> means that your program have failed.
			If it's tagged <Outputs> means that your program have succeed or does not generate error.
			Here is the result : 
			{result}
			You are to generate 2 types of reasoning, reasoning to retry and reasoning to skip and be done with the session.
			You are to put them in xml format. Like these:
			<ReasonsToRetry>
			```yaml
			- "Reason to retry 1"
			- "Reason to retry 2"
			...
			- "Reason to retry N"
			```
			</ReasonsToRetry>
			<ReasonsToStop>
			```yaml
			- "Reason to stop 1"
			- "Reason to stop 2"
			...
			- "Reason to stop N"
			```
			</ReasonsToStop>
			""".strip().format(result=result_str)
		)


class ReasoningYaitsiu:
	"""
	General Algorithm :
	- Initiate system prompt
		- SENSOR: Get numbers of today's followers and assign to system prompt
		- SENSOR: Get follower tweets and assign to user prompt
	- Initiate user prompt to generate reasoning
		- SELF: Initiate a strategy to use and assign to user prompt
			- If there's no cached strategy or all cached strategies have been used, generate new strategies:
				- Generate strategies
				- Cache the strategies
			- If there's a cached strategy that hasn't been used, use it
	- GEN REASON: Assistant to reply with reasonings as of why strategy might work


	Code Gen Algorithm:
	- Loop until max 5 times
		- Initiate user prompt for assistant to generate code from previous reasoning
		- GEN CODE: Assistant to reply with code
		- Initiate user prompt for assistant to generate reasoning of why something will work or not from code
		- GEN REASON: Assistant to reply with reasonings
		- Initiate user prompt for assistant to see the model results, and ask reasoning from the agent to ask if the strategy should continue or not
		- If
			- Code gen fails, continue
			- Code gen fails more than 5 times, summarize the reason why it breaks, break
			- Code gen works, summarize the reason of why it works, break
	"""

	def __init__(
		self,
		db: DB,
		sensor: AgentSensor,
		genner: Genner,
		container_manager: ContainerManager,
	):
		self.db = db
		self.sensor = sensor
		self.chat_history = ChatHistory()
		self.genner = genner
		self.container_manager = container_manager
		self.strategy = ""

	def prepare_system(self) -> ChatHistory:
		ch = ChatHistory()

		follower_count = self.sensor.get_count_of_followers()
		sampled_follower_tweets = self.sensor.get_sample_of_recent_tweets_of_followers()

		ch.messages.append(
			Message(
				role="system",
				content=TwitterPromptGenerator.generate_system_prompt(
					follower_count, sampled_follower_tweets
				),
				metadata={
					"followers_count": follower_count,
					"follower_tweets": sampled_follower_tweets,
				},
			)
		)

		return ch

	def reset(self) -> None:
		self.chat_history = ChatHistory()
		self.strategy = ""

	def get_new_strategy(self) -> Tuple[StrategyData, List[str], ChatHistory]:
		"""
		Algorithm:
		- Get latest non-tried strategy
		- If there's a strategy, use it
		- If there's no strategy, generate new strategies, save this into DB
		"""
		ctx_ch = ChatHistory()
		chosen_strategy = self.db.get_latest_non_tried_strategy()
		new_strategies = []

		if not chosen_strategy:
			previous_strategies = self.db.sample_all_strategies()
			new_strategies, ctx_ch = self.gen_strategies(previous_strategies)
			self.db.insert_strategies(new_strategies)

			chosen_strategy = self.db.get_latest_non_tried_strategy()
			assert chosen_strategy is not None

		return chosen_strategy, new_strategies, ctx_ch

	def gen_strategies(
		self, previous_strategies: List[StrategyData]
	) -> Tuple[List[str], ChatHistory]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=TwitterPromptGenerator.generate_strategy_prompt(
					previous_strategies
				),
			)
		)

		flag = 1
		while flag:
			gen_result = self.genner.generate_list(self.chat_history + ctx_ch)

			if err := gen_result.err():
				logger.error(
					f"ReasoningYaitsiu.gen_strategies, On {flag}-th try: \n{err}"
				)
				flag += 1
				continue

			flag = 0

		processed_list, raw_response = gen_result.unwrap()

		ctx_ch.messages.append(Message(role="assistant", content=raw_response))

		return processed_list[0], ctx_ch

	def gen_strategy_reasoning(self, strategy: StrategyData) -> ChatHistory:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=TwitterPromptGenerator.generate_post_strategy_reasoning_prompt(
					strategy
				),
			)
		)

		flag = 1
		while flag:
			gen_result = self.genner.ch_completion(self.chat_history + ctx_ch)

			if err := gen_result.err():
				logger.error(
					f"ReasoningYaitsiu.gen_strategies, On {flag}-th try: \n{err}"
				)
				continue

			flag = 0

		raw_response = gen_result.unwrap()

		ctx_ch.messages.append(Message(role="assistant", content=raw_response))

		return ctx_ch

	def gen_code(self) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(role="user", content=TwitterPromptGenerator.generate_code_prompt())
		)

		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			logger.error(f"ReasoningYaitsiu.gen_code, generate code failed: \n{err}")
			return Err(f"ReasoningYaitsiu.gen_code, generate code failed: \n{err}")

		processed_code, raw_response = gen_result.unwrap()

		ctx_ch.messages.append(Message(role="assistant", content=raw_response))

		return Ok((processed_code, ctx_ch))

	def gen_code_reasoning(
		self, code_output: str | None, errors: str | None
	) -> Result[Tuple[List[str], List[str], ChatHistory], str]:
		ctx_ch = ChatHistory()

		if errors is not None:
			ctx_ch.messages.append(
				Message(
					role="user",
					content=TwitterPromptGenerator.generate_post_code_reasoning_prompt(
						errors=errors, outputs=None
					),
				)
			)
		else:
			ctx_ch.messages.append(
				Message(
					role="user",
					content=TwitterPromptGenerator.generate_post_code_reasoning_prompt(
						errors=None, outputs=code_output
					),
				)
			)

		reasoning_result = self.genner.ch_completion(self.chat_history + ctx_ch)

		if err := reasoning_result.err():
			logger.info(
				f"ReasoningYaitsiu.gen_code_reasoning: Chat completion failed: \n{err}"
			)
			return Err(
				f"ReasoningYaitsiu.gen_code_reasoning: Chat completion failed: \n{err}"
			)

		reasoning = reasoning_result.unwrap()

		extract_result = self.genner.extract_list(
			reasoning, ["ReasonsToRetry", "ReasonsToStop"]
		)

		if err := extract_result.err():
			logger.info(
				f"ReasoningYaitsiu.gen_code_reasoning, list extraction failed: \n{err}"
			)
			return Err(
				f"ReasoningYaitsiu.gen_code_reasoning, list extraction failed: \n{err}"
			)

		retry_reasons, stop_reasons = extract_result.unwrap()

		ctx_ch.messages.append(Message(role="assistant", content=reasoning))

		return Ok((retry_reasons, stop_reasons, ctx_ch))
