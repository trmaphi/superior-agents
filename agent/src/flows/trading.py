from pprint import pformat
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
    network: str,
    time: str,
    apis: List[str],
    trading_instruments: List[str],
    metric_name: str,
    prev_strat: StrategyData | None,
    notif_str: str | None,
    txn_service_url: str,
    summarizer: Callable[[List[str]], str],
):
    """
    Execute an assisted trading workflow with the trading agent.
    - Orchestrates the complete trading workflow.
    - Handles retries for failed steps and saves the results to the database.

    Args:
            agent (TradingAgent): The trading agent to use
            session_id (str): Identifier for the current session
            role (str): Role of the agent (e.g., "trader")
            network (str): Blockchain network to operate on
            time (str): Time frame for the trading goal
            apis (List[str]): List of APIs available to the agent
            trading_instruments (List[str]): List of available trading instruments
            metric_name (str): Name of the metric to track
            prev_strat (StrategyData | None): Previous strategy, if any
            notif_str (str | None): Notification string to process
            txn_service_url (str): URL of the transaction service
            summarizer (Callable[[List[str]], str]): Function to summarize text

    Returns:
            None: This function doesn't return a value but logs its progress
    """
    agent.reset()
    logger.info("Reset agent")
    logger.info("Starting on assisted trading flow")
    # Store initial metric state to measure performance of trading strategy
    start_metric_state = str(agent.sensor.get_metric_fn(metric_name)())

    try:
        assert notif_str is not None
        related_strategies = agent.rag.relevant_strategy_raw(notif_str)

        assert len(related_strategies) != 0
        most_related_strat = related_strategies[0]

        rag_summary = most_related_strat.summarized_desc
        rag_before_metric_state = most_related_strat.parameters["start_metric_state"]
        rag_after_metric_state = most_related_strat.parameters["end_metric_state"]
        logger.info(f"Using related RAG summary {rag_summary}")
    except (AssertionError, Exception) as e:
        if isinstance(e, Exception):
            logger.warning(f"Error retrieving RAG strategy: {str(e)}")
        # Set default values when RAG retrieval fails to ensure workflow continues
        rag_summary = "Unable to retrieve a relevant strategy from RAG handler..."
        rag_before_metric_state = (
            "Unable to retrieve a relevant strategy from RAG handler..."
        )
        rag_after_metric_state = (
            "Unable to retrieve a relevant strategy from RAG handler..."
        )
        logger.info("Not using any strategy from a RAG...")

    logger.info(f"Using metric: {metric_name}")
    logger.info(f"Current state of the metric: {start_metric_state}")
    agent.chat_history = agent.prepare_system(
        role=role,
        time=time,
        metric_name=metric_name,
        network=network,
        metric_state=start_metric_state,
    )
    logger.info("Initialized system prompt")

    logger.info("Attempt to generate research code...")
    research_code = ""
    err_acc = ""
    regen = False
    success = False
    # Generate and execute market research code with retry mechanism
    for i in range(3):
        try:
            if regen:
                research_code, new_ch = agent.gen_better_code(
                    research_code, err_acc
                ).unwrap()
            else:
                if not prev_strat:
                    research_code, new_ch = agent.gen_research_code_on_first(
                        apis
                    ).unwrap()
                else:
                    research_code, new_ch = agent.gen_research_code(
                        notifications_str=notif_str if notif_str else "Fresh",
                        prev_strategy=prev_strat.summarized_desc if prev_strat else "",
                        apis=apis,
                        rag_summary=rag_summary,
                        before_metric_state=rag_before_metric_state,
                        after_metric_state=rag_after_metric_state,
                    ).unwrap()

            logger.info(f"Response: {new_ch.get_latest_response()}")
            agent.chat_history += new_ch
            agent.db.insert_chat_history(session_id, new_ch)

            code_execution_result = agent.container_manager.run_code_in_con(
                research_code, "trader_research_code"
            )
            research_code_output, _ = code_execution_result.unwrap()

            success = True
            break
        except UnwrapError as e:
            e = e.result.err()
            if regen:
                logger.error(f"Regen failed on research code generation..., err: \n{e}")
            else:
                logger.error(f"Failed on first research code generation..., err: \n{e}")
            regen = True
            err_acc += f"\n{str(e)}"

    if not success:
        logger.info(
            "Failed generating research after 3 times... Stopping this cycle..."
        )
        return
    logger.info("Succeeded in generating research...")
    logger.info(f"Research :\n{research_code_output}")

    logger.info("Attempt to generate strategy...")
    err_acc = ""
    regen = False
    success = False
    # Generate trading strategy based on research findings
    for i in range(3):
        try:
            if regen:
                logger.info("Regenning on strategy..")

            strategy_output, new_ch = agent.gen_strategy(
                notifications_str=notif_str if notif_str else "Fresh",
                research_output_str=research_code_output,
                network=network,
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
        logger.info(
            "Failed generating strategy after 3 times... Stopping this cycle..."
        )
        return
    else:
        logger.info("Succeeded generating strategy")
        logger.info(f"Strategy :\n{strategy_output}")

    logger.info("Generating address research code...")
    address_research_code = ""
    err_acc = ""
    regen = False
    success = False
    # Research blockchain addresses - more retries (10) due to complexity
    for i in range(10):
        try:
            if regen:
                logger.info("Regenning on address research")
                address_research_code, new_ch = agent.gen_better_code(
                    address_research_code, err_acc
                ).unwrap()
            else:
                address_research_code, new_ch = (
                    agent.gen_account_research_code().unwrap()
                )

            logger.info(f"Response: {new_ch.get_latest_response()}")
            agent.chat_history += new_ch
            agent.db.insert_chat_history(session_id, new_ch)

            code_execution_result = agent.container_manager.run_code_in_con(
                address_research_code, "trader_address_research"
            )
            address_research_output, _ = code_execution_result.unwrap()

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
            "Failed generating address research code after 3 times... Stopping this cycle..."
        )
        return

    logger.info("Succeeded address research")
    logger.info(f"Address research: \n{address_research_output}")

    logger.info("Generating some trading code")
    trading_code = ""
    err_acc = ""
    code_output = ""
    success = False
    regen = False
    #  Generate and execute actual trading code based on strategy and research
    for i in range(3):
        try:
            if regen:
                logger.info("Regenning on trading code...")
                trading_code, new_ch = agent.gen_better_code(
                    trading_code, err_acc
                ).unwrap()
            else:
                trading_code, new_ch = agent.gen_trading_code(
                    strategy_output=strategy_output,
                    address_research=address_research_output,
                    apis=apis,
                    trading_instruments=trading_instruments,
                    agent_id=agent.agent_id,
                    txn_service_url=txn_service_url,
                    session_id=session_id,
                ).unwrap()

            logger.info(f"Response: {new_ch.get_latest_response()}")
            agent.chat_history += new_ch
            agent.db.insert_chat_history(session_id, new_ch)

            code_execution_result = agent.container_manager.run_code_in_con(
                trading_code, "trader_trading_code"
            )
            trading_code_output, reflected_code = code_execution_result.unwrap()

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
        logger.info(f"Output: \n{trading_code_output}")

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
            trading_code,
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
                "trading_instruments": trading_instruments,
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
