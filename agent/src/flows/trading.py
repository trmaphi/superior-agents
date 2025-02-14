import sys
from typing import Callable, List

from loguru import logger
from result import UnwrapError
from src.agent.trading import TradingAgent
from src.datatypes import StrategyData, StrategyInsertData


def assisted_flow(
	agent: TradingAgent,
	session_id: str,
	role: str,
	time: str,
	apis: List[str],
	trading_instruments: List[str],
	metric_name: str,
	prev_strat: StrategyData | None,
	notif_str: str,
	txn_service_url: str,
	summarizer: Callable[[List[str]], str],
):
	agent.reset()
	logger.info("Reset agent")
	logger.info("Starting on assisted trading flow")

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
	logger.info(f"Strategy :\n{strategy_output}")

	logger.info("Attempt to generate address research code...")
	code = ""
	err_acc = ""
	regen = False
	success = False
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on address research")
				code, new_ch = agent.gen_better_code(code, err_acc).unwrap()
			else:
				code, new_ch = agent.gen_account_research_code(
					role=role,
					time=time,
					metric_name=metric_name,
					metric_state=metric_state,
				).unwrap()

			logger.info(f"Response: {new_ch.get_latest_response()}")
			agent.chat_history += new_ch
			agent.db.insert_chat_history(session_id, new_ch)

			code_execution_result = agent.container_manager.run_code_in_con(
				code, "trader_market_account_research_on_daily"
			)
			address_research, _ = code_execution_result.unwrap()

			success = True

			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on address research, err: \n{e}")
			else:
				logger.error(f"Failed on first address research code, err: \n{e}")
			regen = True
			err_acc += f"\n{str(e)}"

	if not success:
		logger.info(
			"Failed generating address research code after 3 times... Exiting..."
		)
		sys.exit()

	logger.info("Succeeded address research")
	logger.info(f"Address research \n{address_research}")

	logger.info("Generating some trading code")
	code = ""
	err_acc = ""
	output = None
	success = False
	regen = False
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on trading code...")
				code, new_ch = agent.gen_better_code(code, err_acc).unwrap()
			else:
				code, new_ch = agent.gen_trading_code(
					strategy_output=strategy_output,
					address_research=address_research,
					apis=apis,
					trading_instruments=trading_instruments,
					agent_id=agent.id,
					txn_service_url=txn_service_url,
				).unwrap()

			logger.info(f"Response: {new_ch.get_latest_response()}")
			agent.chat_history += new_ch
			agent.db.insert_chat_history(session_id, new_ch)

			code_execution_result = agent.container_manager.run_code_in_con(
				code, "trader_trade_on_daily"
			)
			output, reflected_code = code_execution_result.unwrap()

			success = True
			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on trading code, err: \n{e}")
			else:
				logger.error(f"Failed on first trading code, err: \n{e}")
			regen = True
			err_acc += f"\n{str(e)}"

	if not success:
		logger.info("Failed generating output of trading code after 3 times...")
	else:
		logger.info("Succeeded generating output of trading code!")
		logger.info(f"Output: \n{output}")

	logger.info("Saving strategy and its result...")
	agent.db.insert_strategy_and_result(
		agent_id=agent.id,
		strategy_result=StrategyInsertData(
			summarized_desc=summarizer([strategy_output]),
			full_desc=strategy_output,
			parameters={
				"apis": apis,
				"trading_instruments": trading_instruments,
				"metric_name": metric_name,
				"metric_state": metric_state,
				"prev_strat": prev_strat.summarized_desc if prev_strat else "",
			},
			strategy_result="failed" if not success else "success",
		),
	)
	logger.info("Saved, quitting and preparing for next run...")


def unassisted_flow(
	agent: TradingAgent,
	session_id: str,
	role: str,
	time: str,
	apis: List[str],
	trading_instruments: List[str],
	metric_name: str,
	prev_strat: StrategyData | None,
	notif_str: str,
	txn_service_url: str,
	summarizer: Callable[[List[str]], str],
):
	agent.reset()
	logger.info("Reset agent")
	logger.info("Starting on unassisted trading flow...")
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
				result = agent.gen_strategy_on_first(apis)
			else:
				result = agent.gen_strategy(
					cur_environment=notif_str,
					prev_strategy=prev_strat.summarized_desc,
					prev_strategy_result=prev_strat.strategy_result,
					apis=apis,
				)

			strategy_output, new_ch = result.unwrap()
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

	logger.info("Generating some trading code")
	output = None
	code = ""
	err_acc = ""
	success = False
	regen = False
	for i in range(3):
		try:
			if regen:
				logger.info("Regenning on trading code...")
				code, new_ch = agent.gen_better_code(code, err_acc).unwrap()
			else:
				code, new_ch = agent.gen_trading_non_address_code(
					strategy_output=strategy_output,
					apis=apis,
					trading_instruments=trading_instruments,
					agent_id=agent.id,
					txn_service_url=txn_service_url,
				).unwrap()

			logger.info(f"Response: {new_ch.get_latest_response()}")
			agent.chat_history += new_ch
			agent.db.insert_chat_history(session_id, new_ch)

			code_execution_result = agent.container_manager.run_code_in_con(
				code, "trader_trade_on_daily"
			)
			output, reflected_code = code_execution_result.unwrap()

			success = True

			break
		except UnwrapError as e:
			e = e.result.err()
			if regen:
				logger.error(f"Regen failed on trading code, err: \n{e}")
			else:
				logger.error(f"Failed on first trading code, err: \n{e}")
			regen = True
			err_acc += f"\n{str(e)}"

	if not success:
		logger.info("Failed generating output of trading code after 3 times...")
	else:
		logger.info("Succeeded generating output of trading code!")
		logger.info(f"Output: \n{output}")

	logger.info("Saving strategy and its result...")
	agent.db.insert_strategy_and_result(
		agent_id=agent.id,
		strategy_result=StrategyInsertData(
			summarized_desc=summarizer([strategy_output]),
			full_desc=strategy_output,
			parameters={
				"apis": apis,
				"trading_instruments": trading_instruments,
				"metric_name": metric_name,
				"metric_state": metric_state,
				"prev_strat": prev_strat,
			},
			strategy_result="failed" if not success else "success",
		),
	)
	logger.info("Saved, quitting and preparing for next run...")
