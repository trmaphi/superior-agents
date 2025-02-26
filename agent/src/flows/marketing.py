import sys
from typing import Callable, List

from loguru import logger
from result import UnwrapError
from src.agent.marketing import MarketingAgent
from src.datatypes import StrategyData, StrategyInsertData


def unassisted_flow(
	agent: MarketingAgent,
	session_id: str,
	role: str,
	time: str,
	apis: List[str],
	metric_name: str,
	prev_strat: StrategyData | None,
	notif_str: str | None,
	summarizer: Callable[[List[str]], str],
):
	agent.reset()
	logger.info("Reset agent")
	logger.info("Starting on unassisted marketing flow...")
	start_metric_state = str(agent.sensor.get_metric_fn(metric_name)())

	if notif_str:
		related_strategies = agent.rag.search(notif_str)
		most_related_strat, score = related_strategies[0]

		rag_summary = most_related_strat.summarized_desc
		rag_before_metric_state = str(
			most_related_strat.parameters.get("start_metric_state", "")
		)
		rag_after_metric_state = str(
			most_related_strat.parameters.get("after_metric_state", "")
		)
		logger.info(
			f"Using related RAG summary with the distance score of {score}: \n{rag_summary}"
		)
	else:
		rag_summary = "Unable to retrieve from RAG"
		rag_before_metric_state = ""
		rag_after_metric_state = ""
		logger.info("Not using RAG summary...")

	logger.info(f"Using metric: {metric_name}")
	logger.info(f"Current state of the metric: {start_metric_state}")
	agent.chat_history = agent.prepare_system(
		role=role, time=time, metric_name=metric_name, metric_state=start_metric_state
	)
	logger.info("Initialized system prompt")

	logger.info("Attempt to generate strategy...")
	code = ""
	err_acc = ""
	regen = False
	success = False
	for i in range(3):
		try:
			if regen:
				if not prev_strat:
					logger.info("Regenning on first strategy...")
				else:
					logger.info("Regenning on strategy..")

			if not prev_strat:
				strategy_output, new_ch = agent.gen_strategy_on_first(apis).unwrap()
			else:
				strategy_output, new_ch = agent.gen_strategy(
					cur_environment=notif_str if notif_str else "Fresh",
					prev_strategy=prev_strat.summarized_desc,
					summarized_prev_code=prev_strat.parameters["summarized_code"],
					prev_code_output=prev_strat.parameters["code_output"],
					apis=apis,
					rag_summary=rag_summary,
					before_metric_state=rag_before_metric_state,
					after_metric_state=rag_after_metric_state,
				).unwrap()

			logger.info(f"Response: {new_ch.get_latest_response()}")

			agent.chat_history += new_ch
			agent.db.insert_chat_history(session_id, new_ch)

			success = True
			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on strategy generation, err: \n{e}")
			else:
				logger.error(f"Failed on first strategy generation, err: \n{e}")
			regen = True
			err_acc += f"\n{str(e)}"

	if not success:
		logger.info("Failed generating strategy after 3 times... Exiting...")
		sys.exit()

	logger.info("Succeeded generating strategy")

	logger.info("Generating some marketing code")
	code_output = ""
	code = ""
	err_acc = ""
	success = False
	regen = False
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on marketing code...")
				code, new_ch = agent.gen_better_code(code, err_acc).unwrap()
			else:
				code, new_ch = agent.gen_marketing_code(
					strategy_output=strategy_output,
					apis=apis,
				).unwrap()

				logger.info(f"Response: {new_ch.get_latest_response()}")

			agent.chat_history += new_ch
			agent.db.insert_chat_history(session_id, new_ch)

			code_execution_result = agent.container_manager.run_code_in_con(
				code, "marketing_market_on_daily"
			)
			output, reflected_code = code_execution_result.unwrap()

			success = True

			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on marketing code, err: \n{e}")
			else:
				logger.error(f"Failed on first marketing code, err: \n{e}")
			regen = True
			err_acc += f"\n{str(e)}"

	if not success:
		logger.info("Failed generating output of marketing code after 3 times...")
	else:
		logger.info("Succeeded generating output of marketing code!")
		logger.info(f"Output: \n{output}")

	end_metric_state = str(agent.sensor.get_metric_fn(metric_name)())
	summarized_state_change = summarizer(
		[
			f"This is the start state {start_metric_state}",
			f"This is the end state {end_metric_state}",
			"Summarize the state changes of the above",
		]
	)
	logger.info("Summarizing state change...")
	logger.info(f"Summarized state change: \n{summarized_state_change}")
	summarized_code = summarizer(
		[
			code,
			"Summarize the code above in points",
		]
	)
	logger.info("Summarizing code...")
	logger.info(f"Summarized code: \n{summarized_code}")

	logger.info("Saving strategy and its result...")
	agent.db.insert_strategy_and_result(
		agent_id=agent.agent_id,
		strategy_result=StrategyInsertData(
			summarized_desc=summarizer([strategy_output]),
			full_desc=strategy_output,
			parameters={
				"apis": apis,
				"trading_instruments": None,
				"metric_name": metric_name,
				"start_metric_state": start_metric_state,
				"end_metric_state": end_metric_state,
				"summarized_state_change": summarized_state_change,
				"summarized_code": summarized_code,
				"code_output": code_output,
				"prev_strat": prev_strat.summarized_desc if prev_strat else "",
			},
			strategy_result="failed" if not success else "success",
		),
	)
	logger.info("Saved, quitting and preparing for next run...")
