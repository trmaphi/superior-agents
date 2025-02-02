import os
from typing import List

import tweepy
from duckduckgo_search import DDGS
from loguru import logger

import docker
from src.agent import ReasoningYaitsiu
from src.container import ContainerManager
from src.db import SqliteDB
from src.genner import get_genner
from src.secret import get_secrets_from_vault
from src.sensor import AgentSensor
from src.twitter import TweepyTwitterClient
from src.llm_functions import summarize
from src.types import AgentState

get_secrets_from_vault()

API_KEY = os.getenv("API_KEY") or ""
API_SECRET = os.getenv("API_KEY_SECRET") or ""
BEARER_TOKEN = os.getenv("BEARER_TOKEN") or ""
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN") or ""
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET") or ""

logger.info(f"API_KEY: {API_KEY[:5]}...{API_KEY[-5:]}")
logger.info(f"API_SECRET: {API_SECRET[:5]}...{API_SECRET[-5:]}")
logger.info(f"BEARER_TOKEN: {BEARER_TOKEN[:5]}...{BEARER_TOKEN[-5:]}")
logger.info(f"ACCESS_TOKEN: {ACCESS_TOKEN[:5]}...{ACCESS_TOKEN[-5:]}")
logger.info(
	f"ACCESS_TOKEN_SECRET: {ACCESS_TOKEN_SECRET[:5]}...{ACCESS_TOKEN_SECRET[-5:]}"
)


def on_daily(agent: ReasoningYaitsiu):
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

	new_ch = agent.prepare_system(
		follower_count,
		sampled_news,
	)
	agent.chat_history += new_ch
	agent.db.insert_chat_history(new_ch)
	logger.info("Prepared agent's system prompt")

	chosen_strategy, new_strategies, new_ch = agent.get_new_strategy()
	agent.chat_history += new_ch
	agent.db.insert_chat_history(new_ch)
	agent.db.insert_strategies(new_strategies)
	logger.info(f"Selected a strategy {chosen_strategy}")

	new_ch = agent.gen_strategy_reasoning(strategy=chosen_strategy)
	agent.chat_history += new_ch
	agent.db.insert_chat_history(new_ch)
	logger.info("Generated reasoning of strategy")

	agent_states: List[AgentState] = []
	list_of_to_retry = []
	list_of_to_stop = []
	for i in range(5):
		gen_code_result = agent.gen_code()
		logger.info("Attempted to generate a code based of reasoning of strategy")

		# If code generation fail, denoted by `err` not being None, tell agent
		if err := gen_code_result.err():
			logger.error(f"Code generation error, err: \n{err}")

			# Generate reasoning until it is parseable
			flag = 1
			while flag:
				reasoning_result = agent.gen_code_retry_reasoning(None, err)
				logger.info(
					f"{flag}-th attempt to reasoning of code of why it should continue or not"
				)

				if err := reasoning_result.err():
					logger.error(
						f"Reasoning generation error, on {flag}-th try, err: \n{err}"
					)
					flag += 1
					continue

				flag = 0

			# Gen code failed, there's reasoning, continue in the next loop with the new chat history
			reasons_to_retry, reasons_to_stop, new_ch = reasoning_result.unwrap()

			list_of_to_retry.extend(reasons_to_retry)
			list_of_to_stop.extend(reasons_to_stop)

			agent.chat_history += new_ch
			agent.db.insert_chat_history(new_ch)

			agent_states.append(AgentState.FAILED_GENERATION)

			continue

		# Otherwise, code has generated successfully,
		code, new_ch = gen_code_result.unwrap()
		agent.chat_history += new_ch
		agent.db.insert_chat_history(new_ch)

		# Check if the code can run
		run_result = agent.container_manager.run_code_in_con(code, "on_daily")
		logger.info("Attempted to run the code")

		# If code running fail, denoted by `err` not being None, tell agent
		if err := run_result.err():
			logger.error(f"Code run error, err: \n{err}")

			# Generate reasoning until it is parseable
			flag = 1
			while flag:
				reasoning_result = agent.gen_code_retry_reasoning(None, err)
				logger.info(
					f"{flag}-th attempt to reasoning of code of why it should continue or not"
				)

				if err := reasoning_result.err():
					logger.error(
						f"Reasoning generation error, on {flag}-th try, err: \n{err}"
					)
					flag += 1
					continue

				flag = 0

			# Gen code succeeded, but failed to run, there's reasoning, asks if it wants to retry or not
			reasons_to_retry, reasons_to_stop, new_ch = reasoning_result.unwrap()

			list_of_to_retry.extend(reasons_to_retry)
			list_of_to_stop.extend(reasons_to_stop)

			agent.chat_history += new_ch
			agent.db.insert_chat_history(new_ch)
			agent_states.append(AgentState.FAILED_EXECUTION)

			# If the agent thinks there's more reason to retry generating, than stopping
			if len(reasons_to_retry) >= len(reasons_to_stop):
				logger.info(
					"Reason to retry is larger than reason to stop, continuing.."
				)
				continue
			# Otherwise, stop this whole flow
			else:
				logger.info("Reason to stop is larger than reason to retry, stopping..")
				break

		# Otherwise, code has been executed succesfully
		output, reflected_code = run_result.unwrap()

		# Even if the code had succeeded, we want to find out why is that, based upon the output
		flag = 1
		while flag:
			reasoning_result = agent.gen_code_retry_reasoning(output, None)

			if err := reasoning_result.err():
				logger.error(
					f"Reasoning generation error, on {flag}-th try, err: \n{err}"
				)
				flag += 1
				continue

			flag = 0

		# Gen code succeeded, but got to run, there's reasoning, asks if it wants to work upon it better or not
		reasons_to_retry, reasons_to_stop, new_ch = reasoning_result.unwrap()

		list_of_to_retry.extend(reasons_to_retry)
		list_of_to_stop.extend(reasons_to_stop)

		agent.chat_history += new_ch
		agent.db.insert_chat_history(new_ch)

		# If the agent thinks there's more reason to retry generating, then continue
		if len(reasons_to_retry) >= len(reasons_to_stop):
			logger.info("Reason to retry is larger than reason to stop, continuing..")
			agent_states.append(AgentState.SUCCESS_NEEDS_IMPROVEMENT)
			continue
		# Otherwise, stop this whole flow
		else:
			logger.info("Reason to stop is larger than reason to retry, stopping..")
			agent_states.append(AgentState.SUCCESS_WITH_OUTPUT)
			break

	logger.info("Agent on daily run had stopped")
	logger.info(f"It's last state was {agent_states[-1]}")

	if agent_states[-1].is_success:
		logger.info(
			"On daily agent had successfuly executed a code with proper execution result"
		)
		logger.info(f"Because the run is successful, It's outputs are: {output}")
		summarized_reasoning = summarize(genner, list_of_to_retry)
		logger.info(
			f"And here is the aggregate of summarized retry reason of the agent {summarized_reasoning}"
		)
	else:
		logger.info("On daily agent has failed generating proper code.")
		summarized_reasoning = summarize(genner, list_of_to_stop)
		logger.info(
			f"And here is the aggregate of summarized sotp reasons of the agent {summarized_reasoning}"
		)

	agent.db.mark_strategy_as_done(
		str(chosen_strategy.idx),
		strategy_result="success" if agent_states[-1].is_success else "failure",
		reasoning=summarized_reasoning,
	)


if __name__ == "__main__":
	auth = tweepy.OAuth1UserHandler(
		consumer_key=API_KEY,
		consumer_secret=API_SECRET,
	)
	auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)

	ddgs = DDGS()
	db = SqliteDB()
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
	sensor = AgentSensor(twitter_client, ddgs)
	genner = get_genner(backend="qwen")
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

	agent = ReasoningYaitsiu(
		db=db, sensor=sensor, genner=genner, container_manager=container_manager
	)

	on_daily(agent)
