import json
import os
import sys
from typing import List

from dotenv import load_dotenv
import requests
from result import UnwrapError
import tweepy
from duckduckgo_search import DDGS
from loguru import logger
from anthropic import Anthropic as DeepSeekClient
from anthropic import Anthropic
from openai import OpenAI as DeepSeek

import docker
from src.agent.marketing import MarketingAgent, MarketingPromptGenerator
from src.container import ContainerManager
from src.db.marketing import MarketingDB
from src.genner import get_genner
from src.helper import services_to_envs, services_to_prompts

# from src.secret import get_secrets_from_vault
from src.sensor.marketing import MarketingSensor
from src.twitter import TweepyTwitterClient

# get_secrets_from_vault()
load_dotenv()

TWITTER_API_KEY = os.getenv("API_KEY") or ""
TWITTER_API_SECRET = os.getenv("API_KEY_SECRET") or ""
TWITTER_ACCESS_TOKEN = os.getenv("BEARER_TOKEN") or ""
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN") or ""
TWITTER_BEARER_TOKEN = os.getenv("ACCESS_TOKEN_SECRET") or ""

os.environ["TWITTER_API_KEY"] = TWITTER_API_KEY
os.environ["TWITTER_API_SECRET"] = TWITTER_API_SECRET
os.environ["TWITTER_ACCESS_TOKEN"] = TWITTER_ACCESS_TOKEN
os.environ["TWITTER_ACCESS_TOKEN_SECRET"] = TWITTER_ACCESS_TOKEN_SECRET
os.environ["TWITTER_BEARER_TOKEN"] = TWITTER_BEARER_TOKEN

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or ""
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY") or ""
DEEPSEEK_KEY_2 = os.getenv("DEEPSEEK_KEY_2") or ""


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

	logger.info("Attempt to generate market research code...")
	success = False
	regen = False
	code = ""
	err_acc = ""
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on market research code")
				code, new_ch = agent.gen_better_code(code, err_acc).unwrap()
				logger.info(
					f"Regenned with this response: \n{new_ch.messages[-1].content}"
				)
				agent.chat_history += new_ch
			else:
				code, new_ch = agent.gen_market_research_code(
					follower_count, None, apis
				).unwrap()
				logger.info(
					f"Generated marketing research code with this response: \n{new_ch.messages[-1].content}"
				)
				agent.chat_history += new_ch

			market_research, reflected_code = agent.container_manager.run_code_in_con(
				code, "marketing_research_on_daily"
			).unwrap()

			success = True
			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(
					f"Regen failed on market research code, caused by err: \n{e}"
				)
			else:
				logger.error(f"Failed on first market research code genning: \n{e}")
			err_acc += f"\n{str(e)}"

			regen = True

	if not success:
		logger.error("Failed generating market research code")
		raise

	logger.info("Succeeded market research")
	logger.info(f"Market research :\n{market_research}")

	logger.info("Attempt to generate strategy...")
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
		logger.error("Failed generating strategy...")
		raise

	logger.info("Succeeded generating strategy")
	logger.info(f"Strategy :\n{chosen_strategy}")

	logger.info("Attempt to generate marketing code...")
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

	if success:
		logger.info("Code executed!")
		logger.info(f"Output: \n{output}")
	else:
		logger.info("Code failed after 3 regen tries! Stopping...")


def on_notification(agent: MarketingAgent, notification: str):
	pass


if __name__ == "__main__":
	deepseek_client = DeepSeek(
		base_url="https://openrouter.ai/api/v1", api_key=DEEPSEEK_KEY
	)
	deepseek_2_client = DeepSeekClient(api_key=DEEPSEEK_KEY_2)
	anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

	HARDCODED_BASE_URL = "http://34.87.43.255:4999"

	# Collect args[1] as session id
	session_id = sys.argv[1]

	logger.info(f"Session ID: {session_id}")

	# Connect to SSE endpoint to get session logs
	url = f"{HARDCODED_BASE_URL}/sessions/{session_id}/logs"
	headers = {"Accept": "text/event-stream"}
	logger.info("Marketing start")

	# Initialize fe_data with default values
	fe_data = {
		"model": "deepseek_2",
		"research_tools": [
			"CoinGecko",
			"DuckDuckGo",
			"Etherscan",
			"Infura",
		],
		"prompts": {},  # Ensure this stays as a dictionary
		"trading_instruments": [],
	}

	try:
		response = requests.get(url, headers=headers, stream=True)

		for line in response.iter_lines():
			if line:
				decoded_line = line.decode("utf-8")
				if decoded_line.startswith("data: "):
					data = json.loads(decoded_line[6:])
					if "logs" in data:
						log_entries = data["logs"].strip().split("\n")
						if log_entries:
							first_log = json.loads(log_entries[0])
							if first_log["type"] == "request":
								logger.info("Processing initial prompt payload")

								payload = json.loads(
									json.dumps(first_log["payload"], indent=2)
								)

								# Update non-prompt fields
								if "model" in payload:
									fe_data["model"] = payload["model"]

								if "research_tools" in payload and isinstance(
									payload["research_tools"], list
								):
									fe_data["research_tools"] = payload[
										"research_tools"
									]

								if "trading_instruments" in payload and isinstance(
									payload["trading_instruments"], list
								):
									fe_data["trading_instruments"] = payload[
										"trading_instruments"
									]

								# Handle custom prompts
								if "prompts" in payload and isinstance(
									payload["prompts"], list
								):
									# Convert list of prompt dicts to name:prompt dictionary
									received_prompts = {
										item["name"]: item["prompt"]
										for item in payload["prompts"]
										if isinstance(item, dict)
										and "name" in item
										and "prompt" in item
									}
									fe_data["prompts"].update(received_prompts)

								logger.info("Received frontend data with prompts:")
								logger.info(
									f"Received prompts: {list(fe_data['prompts'].keys())}"
								)
								break

		# Get default prompts
		default_prompts = MarketingPromptGenerator.get_default_prompts()
		logger.info(f"Available default prompts: {list(default_prompts.keys())}")

		# Only fill in missing prompts from defaults
		missing_prompts = set(default_prompts.keys()) - set(fe_data["prompts"].keys())
		if missing_prompts:
			logger.info(f"Adding missing default prompts: {list(missing_prompts)}")
			for key in missing_prompts:
				fe_data["prompts"][key] = default_prompts[key]
	except Exception as e:
		logger.error(f"Error fetching session logs: {e}, going with defaults")
		# In case of error, return fe_data with default prompts
		default_prompts = MarketingPromptGenerator.get_default_prompts()
		fe_data["prompts"].update(default_prompts)
	
	logger.info(f"Final prompts: {fe_data["prompts"]}")

	services_used = fe_data["research_tools"]
	model_name = "deepseek_2"
	in_con_env = services_to_envs(services_used)
	apis = services_to_prompts(services_used)

	auth = tweepy.OAuth1UserHandler(
		consumer_key=TWITTER_API_KEY,
		consumer_secret=TWITTER_API_SECRET,
	)
	auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)

	ddgs = DDGS()
	db = MarketingDB()
	twitter_client = TweepyTwitterClient(
		client=tweepy.Client(
			bearer_token=TWITTER_BEARER_TOKEN,
			consumer_key=TWITTER_API_KEY,
			consumer_secret=TWITTER_API_SECRET,
			access_token=TWITTER_ACCESS_TOKEN,
			access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
		),
		api_client=tweepy.API(auth),
	)
	sensor = MarketingSensor(twitter_client, ddgs)

	genner = get_genner(
		model_name,
		deepseek_client=deepseek_client,
		anthropic_client=anthropic_client,
		deepseek_2_client=deepseek_2_client,
	)
	docker_client = docker.from_env()
	container_manager = ContainerManager(
		docker_client, "twitter_agent_executor", "./code", in_con_env=in_con_env
	)
	prompt_generator = MarketingPromptGenerator(fe_data["prompts"])

	agent = MarketingAgent(
		db=db,
		sensor=sensor,
		genner=genner,
		container_manager=container_manager,
		prompt_generator=prompt_generator,
	)

	on_daily(agent)
