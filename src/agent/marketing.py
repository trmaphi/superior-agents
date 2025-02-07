import re
from textwrap import dedent
from typing import Dict, List, Optional, Tuple

from result import Err, Ok, Result

from src.container import ContainerManager
from src.datatypes import StrategyData
from src.datatypes.marketing import NewsData
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

		Required prompt keys:
		- system_prompt_tweets
		- system_prompt_news
		- strategy_prompt
		- code_prompt
		- regen_code_prompt
		"""
		self.prompts = prompts if prompts else self.get_default_prompts()
		self._validate_prompts(self.prompts)

	def _validate_prompts(self, prompts: Dict[str, str]) -> None:
		"""
		Validate prompts for required and unexpected placeholders.

		Args:
			prompts: Dictionary of prompt name to prompt content

		Raises:
			ValueError: If prompts are missing required placeholders or contain unexpected ones
		"""
		required_placeholders = {
			"system_prompt_tweets": {"{followers_count}", "{follower_tweets}"},
			"system_prompt_news": {"{followers_count}", "{news}"},
			"research_code_prompt": {"{portfolio}", "{apis_str}"},
			"strategy_prompt": {"{prev_strats}"},
			"code_prompt": set(),  # No placeholders required
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

	def generate_system_prompt_tweets(
		self, followers_count: int, follower_tweets: List["TweetData"]
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
		return self.prompts["system_prompt_tweets"].format(
			followers_count=followers_count, follower_tweets=follower_tweets_str
		)

	def generate_system_prompt_news(
		self, followers_count: int, news: List["NewsData"]
	) -> str:
		formatted_news = []
		for new in news[:5]:
			new_yaml = dedent(f"""
				-   title: "{new.title}"
					body: "{new.body}"
					source: "{new.source}"
					url: "{new.url}"
					date: "{new.date}"
			""").strip()
			formatted_news.append(new_yaml)

		formatted_news_str = "\n".join(formatted_news)
		return self.prompts["system_prompt_news"].format(
			followers_count=followers_count, news=formatted_news_str
		)

	def generate_research_code_prompt(
		self, followers: int, prev_strat: StrategyData | None, apis: List[str]
	) -> str:
		apis_str = ",\n".join(apis)

		prev_strat_str = (
			str(prev_strat) if prev_strat else "No strategies tried yesterday"
		)

		return self.prompts["research_code_prompt"].format(
			followers=str(followers),
			apis_str=apis_str,
			prev_strat=prev_strat_str,
		)

	def generate_strategy_prompt(self, prev_strats: List["StrategyData"]) -> str:
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

		return self.prompts["strategy_prompt"].format(prev_strats=prev_strats_str)

	def generate_code_prompt(self) -> str:
		return self.prompts["code_prompt"]

	def regen_code(self, previous_code: str, errors: str) -> str:
		return self.prompts["regen_code_prompt"].format(
			errors=errors, previous_code=previous_code
		)

	@staticmethod
	def get_default_prompts() -> Dict[str, str]:
		"""Get the complete set of default prompts that can be customized."""
		return {
			"system_prompt_tweets": dedent("""
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
			""").strip(),
			"system_prompt_news": dedent("""
				You are a marketing agent in twitter/X.
				You have {followers_count} followers.
				Your goal is to maximize the number of followers you have.
				You are tasked with generating strategies, reasoning, and code to achieve this.
				You are also assisted by these sampled crypto news:
				<FormattedNews>
				```yaml
				{news}
				```
				</FormattedNews>
			""").strip(),
			"strategy_prompt": dedent("""
				You are a marketing agent in twitter/X.
				This is the previous strats that you have generated, and it's results:
				<PrevStrats>
				```yaml
				{prev_strats}
				```
				</PrevStrats>
				You are to generate strategies that might perform better than those that you have generated, or the same if you think it's good enough.
				Please generate new strategy.
			""").strip(),
			#
			"research_code_prompt": dedent("""
				You are a social media influencer on Twitter/x.com. Your goal is to have more followers in 24 hours than now.
				Currently you have {followers} followers.
				Yesterday you tried
				<YesterdayStrategy>
				{prev_strat_str}
				</YesterdayStrategy>
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
			"""),
			#
			"code_prompt": dedent("""
				You are a marketing agent in twitter/X.
				Above is your reasoning on why you think the strategy will work and why it will not.
				Generate code from the reasonings that you have generated.
				You are to use private keys using the library `dotenv` and use those environment variables to authenticate with the Twitter API.
				You have access to the following APIs:
				<APIs>
				{apis_str}
				</APIs>
				You are to use tweepy or direct twitter HTTP api to execute your strategy.
				You are to raise every error that is catch able rather than doing silent error.
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
				Please generate the code.
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


class MarketingAgent:
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
		db: MarketingDB,
		sensor: MarketingSensor,
		genner: Genner,
		container_manager: ContainerManager,
		prompt_generator: MarketingPromptGenerator,
	):
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

	def prepare_system(
		self,
		follower_count: int,
		sampled_news: List[NewsData] | None = None,
		sampled_tweets: List[TweetData] | None = None,
	) -> ChatHistory:
		ctx_ch = ChatHistory()

		if sampled_news is not None:
			ctx_ch = ctx_ch.append(
				Message(
					role="system",
					content=self.prompt_generator.generate_system_prompt_news(
						follower_count, sampled_news
					),
					metadata={
						"followers_count": follower_count,
						# "follower_tweets": sampled_follower_tweets,
						"sampled_news": sampled_news,
					},
				)
			)
		elif sampled_tweets is not None:
			ctx_ch = ctx_ch.append(
				Message(
					role="system",
					content=self.prompt_generator.generate_system_prompt_tweets(
						follower_count, sampled_tweets
					),
					metadata={
						"followers_count": follower_count,
						"follower_tweets": sampled_tweets,
					},
				)
			)
		else:
			raise ValueError("Both sampled_news and sampled_tweets cannot be None")

		return ctx_ch

	def get_strategy(
		self,
	) -> Result[Tuple[StrategyData, ChatHistory], str]:
		"""
		Algorithm:
		- Get latest non-tried strategy
		- If there's a strategy, use it
		- If there's no strategy, generate new strategies, save this into DB
		"""
		ctx_ch = ChatHistory()
		chosen_strategy = self.db.get_latest_non_tried_strategy()

		if chosen_strategy:
			return Ok((chosen_strategy, ctx_ch))

		previous_strategies = self.db.sample_all_strategies()
		gen_strat_result = self.gen_strategy(previous_strategies)

		if err := gen_strat_result.err():
			return Err(
				f"MarketingAgent.get_new_strategy, gen strategy failed, err: \n{err}"
			)

		new_strat, new_ch = gen_strat_result.unwrap()
		ctx_ch += new_ch
		self.db.insert_strategies([new_strat])

		new_strat_obj = StrategyData(
			name=new_strat,
		)

		return Ok((new_strat_obj, ctx_ch))
	
	def gen_market_research_code(
		self, followers: int, prev_strat: StrategyData | None, apis: List[str]
	):
		

	def gen_strategy(
		self, previous_strategies: List[StrategyData]
	) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(
				role="user",
				content=self.prompt_generator.generate_strategy_prompt(
					previous_strategies
				),
				metadata={"previous_strategies": previous_strategies},
			)
		)

		gen_result = self.genner.ch_completion(self.chat_history + ctx_ch)

		if err := gen_result.err():
			return Err(
				f"MarketingAgent.gen_strategy, chat completion failed, caused by err: \n{err} "
			)

		strategy = gen_result.unwrap()

		ctx_ch = ctx_ch.append(
			Message(
				role="assistant",
				content=strategy,
			)
		)

		return Ok((strategy, ctx_ch))

	def gen_marketing_code(self) -> Result[Tuple[str, ChatHistory], str]:
		ctx_ch = ChatHistory(
			Message(role="user", content=self.prompt_generator.generate_code_prompt())
		)

		gen_result = self.genner.generate_code(self.chat_history + ctx_ch)

		if err := gen_result.err():
			return Err(f"MarketingAgent.gen_code, generate code failed: \n{err}")

		processed_code, raw_response = gen_result.unwrap()

		ctx_ch = ctx_ch.append(
			Message(
				role="assistant",
				content=raw_response,
				metadata={"processed_code": processed_code},
			)
		)

		return Ok((processed_code[0], ctx_ch))

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
				f"TradingAgent.gen_better_code, failed on regenerating code, err: \n{err}"
			)

		processed_codes, raw_response = gen_result.unwrap()
		ctx_ch = ctx_ch.append(Message(role="assistant", content=raw_response))

		return Ok((processed_codes[0], ctx_ch))
