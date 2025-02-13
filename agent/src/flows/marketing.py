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
	notif_str: str,
	summarizer: Callable[[List[str]], str],
):
	agent.reset()
	logger.info("Reset agent")
	logger.info("Starting on unassisted marketing flow...")
	metric_state = str(agent.sensor.get_metric_fn(metric_name)())

	logger.info(f"Using metric: {metric_name}")
	logger.info(f"Current state of the metric: {metric_state}")
	agent.chat_history = agent.prepare_system(
		role=role, time=time, metric_name=metric_name, metric_state=metric_state
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
					cur_environment=notif_str,
					prev_strategy=prev_strat.summarized_desc,
					prev_strategy_result=prev_strat.strategy_result,
					apis=apis,
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
	output = None
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
				gen_code_result = agent.gen_marketing_code(
					strategy_output=strategy_output,
					apis=apis,
				)

				code, new_ch = gen_code_result.unwrap()
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

	logger.info("Saving strategy and its result...")

	agent.db.insert_strategy_and_result(
		agent_id=agent.id,
		strategy_result=StrategyInsertData(
			summarized_desc=summarizer([strategy_output]),
			full_desc=strategy_output,
			parameters={
				"apis": apis,
				"metric_name": metric_name,
				"metric_state": metric_state,
				"prev_strat": prev_strat,
			},
			strategy_result="failed" if not success else "success",
		),
	)
	logger.info("Saved, quitting and preparing for next run...")
