import os
from typing import List

from result import UnwrapError
import tweepy
from duckduckgo_search import DDGS
from loguru import logger
from anthropic import Anthropic as DeepSeek2

import docker
from src.agent.marketing import MarketingAgent
from src.container import ContainerManager
from src.datatypes.marketing import MarketingAgentState
from src.db.marketing import MarketingDB
from src.genner import get_genner
from src.llm_functions import summarize
from src.secret import get_secrets_from_vault
from src.sensor.marketing import MarketingSensor
from src.twitter import TweepyTwitterClient

get_secrets_from_vault()

API_KEY = os.getenv("API_KEY") or ""
API_SECRET = os.getenv("API_KEY_SECRET") or ""
BEARER_TOKEN = os.getenv("BEARER_TOKEN") or ""
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN") or ""
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET") or ""

CLAUDE_KEY = os.getenv("CLAUDE_KEY") or ""
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY") or ""
DEEPSEEK_KEY_2 = os.getenv("DEEPSEEK_KEY_2") or ""

logger.info(f"API_KEY: {API_KEY[:5]}...{API_KEY[-5:]}")
logger.info(f"API_SECRET: {API_SECRET[:5]}...{API_SECRET[-5:]}")
logger.info(f"BEARER_TOKEN: {BEARER_TOKEN[:5]}...{BEARER_TOKEN[-5:]}")
logger.info(f"ACCESS_TOKEN: {ACCESS_TOKEN[:5]}...{ACCESS_TOKEN[-5:]}")
logger.info(
	f"ACCESS_TOKEN_SECRET: {ACCESS_TOKEN_SECRET[:5]}...{ACCESS_TOKEN_SECRET[-5:]}"
)


def on_daily(agent: MarketingAgent):
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
	agent.reset()
	logger.info("Resetted agent")

	follower_count = agent.sensor.get_count_of_followers()
	# sampled_tweets = self.sensor.get_sample_of_recent_tweets_of_followers()
	sampled_news = agent.sensor.get_news_data()

	# Mutates here
	agent.chat_history = agent.prepare_system(
		follower_count,
		sampled_news=sampled_news,
	)
	logger.info(agent.chat_history.messages[-1].content)
	agent.db.insert_chat_history(agent.chat_history)
	logger.info("Prepared agent's system prompt")

	success = False
	regen = False
	err_acc = ""
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on strategy data")

			chosen_strategy, new_ch = agent.get_strategy().unwrap()
			if len(new_ch.messages) > 0:
				logger.info(f"Generated new strategy, {new_ch.messages[-1].content}")

			agent.chat_history += new_ch

			agent.db.insert_chat_history(new_ch)
			logger.info(f"Selected a strategy, strat: \n{chosen_strategy}")

			success = True

			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on strategy getting, caused by err: \n{e}")
			else:
				logger.error(f"Failed on first strategy getting: \n{e}")
			err_acc += f"\n{str(e)}"

			regen = True

	if not success:
		logger.error("Failed generating strategy ")
		raise

	regen = False
	code = ""
	err_acc = ""
	success = False
	for i in range(5):
		try:
			if regen:
				logger.info(f"Regenning with causing error err: \n{err_acc}")
				code, new_ch = agent.gen_better_code(code, err_acc).unwrap()
				logger.info(
					f"Regenned with this response: \n{new_ch.messages[-1].content}"
				)
				agent.chat_history += new_ch
			else:
				code, new_ch = agent.gen_marketing_code().unwrap()
				logger.info(
					f"Generated marketing code with this response: \n{new_ch.messages[-1].content}"
				)
				agent.chat_history += new_ch

			output, reflected_code = agent.container_manager.run_code_in_con(
				code, "marketing_on_daily"
			).unwrap()

			success = True
			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on strategy getting, caused by err: \n{e}")
			else:
				logger.error(f"Failed on first strategy getting: \n{e}")
			err_acc += f"\n{str(e)}"

			regen = True

	if not success:
		logger.error("Failed generating strategy ")
		raise

	logger.info(f"Success: {success}")
	if success:
		logger.info(f"Output: \n{output}")


if __name__ == "__main__":
	auth = tweepy.OAuth1UserHandler(
		consumer_key=API_KEY,
		consumer_secret=API_SECRET,
	)
	auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)

	ddgs = DDGS()
	db = MarketingDB()
	twitter_client = TweepyTwitterClient(
		client=tweepy.Client(
			bearer_token=BEARER_TOKEN,
			consumer_key=API_KEY,
			consumer_secret=API_SECRET,
			access_token=ACCESS_TOKEN,
			access_token_secret=ACCESS_TOKEN_SECRET,
		),
		api_client=tweepy.API(auth),
	)
	sensor = MarketingSensor(twitter_client, ddgs)
	deepseek_2 = DeepSeek2(api_key=DEEPSEEK_KEY_2)

	genner = get_genner(backend="deepseek_2", deepseek_2_client=deepseek_2)
	docker_client = docker.from_env()
	container_manager = ContainerManager(
		docker_client,
		"twitter_agent_executor",
		"./code",
		{
			"API_KEY": API_KEY,
			"API_SECRET": API_SECRET,
			"BEARER_TOKEN": BEARER_TOKEN,
			"ACCESS_TOKEN": ACCESS_TOKEN,
			"ACCESS_TOKEN_SECRET": ACCESS_TOKEN_SECRET,
		},
	)

	agent = MarketingAgent(
		db=db, sensor=sensor, genner=genner, container_manager=container_manager
	)

	on_daily(agent)
