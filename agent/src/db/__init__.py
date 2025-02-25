from dataclasses import dataclass
from typing import Dict, Any, Optional, List, TypeVar, cast, Generic
from loguru import logger
import requests
import json
from enum import Enum
from datetime import datetime, timedelta

from src.datatypes import StrategyData, StrategyInsertData
from src.types import ChatHistory
from src.helper import get_latest_notifications_by_source

T = TypeVar("T")


class ApiError(Exception):
	pass


@dataclass
class ApiResponse(Generic[T]):
	success: bool
	data: Optional[T]
	error: Optional[str]


class APIDB:
	def __init__(self, base_url: str, api_key: str):
		self.base_url = base_url
		self.headers = {"x-api-key": api_key, "Content-Type": "application/json"}

	def _make_request(
		self, endpoint: str, data: Dict[str, Any], response_type: type[T]
	) -> ApiResponse[T]:
		try:
			response = requests.post(
				f"{self.base_url}/{endpoint}", headers=self.headers, json=data
			)
			response.raise_for_status()
			return ApiResponse(success=True, data=cast(T, response.json()), error=None)
		except requests.exceptions.RequestException as e:
			return ApiResponse(success=False, data=None, error=str(e))

	def fetch_params_using_agent_id(self, agent_id: str) -> Dict[str, Dict[str, Any]]:
		agent_response = self._make_request(
			"agent/get", {"id": agent_id}, Dict[str, Any]
		)
		if not agent_response.success:
			raise ApiError(f"Failed to verify agent: {agent_response.error}")

		strategies_response = self._make_request(
			"strategies/get", {}, List[Dict[str, Any]]
		)
		if not strategies_response.success:
			raise ApiError(f"Failed to fetch strategies: {strategies_response.error}")

		strategies = strategies_response.data or []
		agent_strategies = [s for s in strategies if s.get("agent_id") == agent_id]

		params: Dict[str, Dict[str, Any]] = {}
		for strategy in agent_strategies:
			try:
				strategy_id = str(strategy["id"])
				params[strategy_id] = {
					"parameters": json.loads(strategy["parameters"]),
					"summarized_desc": str(strategy["summarized_desc"]),
					"full_desc": str(strategy["full_desc"]),
				}
			except (KeyError, json.JSONDecodeError, ValueError) as e:
				raise ApiError(
					f"Error processing strategy {strategy.get('id')}: {str(e)}"
				)

		return params

	def insert_strategy_and_result(
		self, agent_id: str, strategy_result: StrategyInsertData
	) -> bool:
		# Verify agent exists
		agent_response = self._make_request(
			"agent/get", {"id": agent_id}, Dict[str, Any]
		)
		if not agent_response.success:
			raise ApiError(f"Failed to verify agent: {agent_response.error}")

		# Build strategy data dictionary, handling optional fields
		strategy_data = {
			"agent_id": agent_id,
		}

		# Add optional fields if they exist
		if strategy_result.summarized_desc is not None:
			strategy_data["summarized_desc"] = strategy_result.summarized_desc

		if strategy_result.full_desc is not None:
			strategy_data["full_desc"] = strategy_result.full_desc

		if strategy_result.parameters is not None:
			strategy_data["parameters"] = json.dumps(strategy_result.parameters)

		if strategy_result.strategy_result is not None:
			strategy_data["strategy_result"] = strategy_result.strategy_result

		# Make API request to create strategy
		response = self._make_request(
			"strategies/create", strategy_data, Dict[str, Any]
		)
		if not response.success:
			raise ApiError(f"Failed to insert strategy: {response.error}")

		return True

	def fetch_latest_strategy(self, agent_id: str) -> Optional[StrategyData]:
		strategies_response = self._make_request(
			"strategies/get",
			{},
			Dict[str, List[Dict[str, Any]]],  # Changed from List[Dict[str, Any]]
		)
		if not strategies_response.success or not strategies_response.data:
			raise ApiError(f"Failed to fetch strategies: {strategies_response.error}")

		strategies = strategies_response.data["data"]

		agent_strategies = [s for s in strategies if s.get("agent_id") == agent_id]

		if not agent_strategies:
			return None

		latest = max(agent_strategies, key=lambda s: s.get("strategy_id", ""))

		return StrategyData(
			strategy_id=str(latest["strategy_id"]),
			agent_id=agent_id,
			parameters=json.loads(latest["parameters"]),
			summarized_desc=str(latest["summarized_desc"]),
			strategy_result=latest["strategy_result"],
			full_desc=str(latest["full_desc"]),
		)

	def fetch_all_strategies(self, agent_id: str) -> List[StrategyData]:
		strategies_response = self._make_request(
			"strategies/get",
			{},
			Dict[str, List[Dict[str, Any]]],  # Changed from List[Dict[str, Any]]
		)
		if not strategies_response.success or not strategies_response.data:
			raise ApiError(f"Failed to fetch strategies: {strategies_response.error}")

		strategies = strategies_response.data["data"]

		agent_strategies = [
			StrategyData(
				strategy_id=str(strat["strategy_id"]),
				agent_id=agent_id,
				parameters=json.loads(strat["parameters"]),
				summarized_desc=str(strat["summarized_desc"]),
				strategy_result=strat["strategy_result"],
				full_desc=str(strat["full_desc"]),
			)
			for strat in strategies
			if strat.get("agent_id") == agent_id
		]

		return agent_strategies

	def insert_chat_history(
		self,
		session_id: str,
		chat_history: ChatHistory,
		base_timestamp: Optional[str] = None,
	) -> bool:
		current_time = datetime.utcnow()

		if base_timestamp:
			try:
				current_time = datetime.strptime(base_timestamp, "%Y-%m-%d %H:%M:%S")
			except ValueError:
				raise ValueError(
					"base_timestamp must be in format 'YYYY-MM-DD HH:MM:SS'"
				)

		for i, message in enumerate(chat_history.messages):
			# Create timestamp for each message, adding 1 second intervals if no base_timestamp provided
			message_time = (current_time + timedelta(seconds=i)).strftime(
				"%Y-%m-%d %H:%M:%S"
			)

			chat_data = {
				"session_id": session_id,
				"message_type": message.role,
				"content": message.content,
				"timestamp": message_time,
			}

			# Add metadata if it exists
			if message.metadata:
				chat_data["metadata"] = json.dumps(message.metadata)

			# Make API request to create chat history entry
			response = self._make_request(
				"chat_history/create", chat_data, Dict[str, Any]
			)
			if not response.success:
				raise ApiError(f"Failed to insert chat message: {response.error}")

		return True

	def fetch_latest_notification_str(self, sources: List[str]) -> str:
		notification_response = self._make_request(
			"notification/get",
			{},
			Dict[str, List[Dict[str, Any]]],  # Changed from List[Dict[str, Any]]
		)
		if not notification_response.success or not notification_response.data:
			raise ApiError(f"Failed to fetch strategies: {notification_response.error}")

		notifications = notification_response.data["data"]

		filtered_notifications = get_latest_notifications_by_source(notifications)

		ret = "\n".join([notif["short_desc"] for notif in filtered_notifications])

		return ret

	def get_agent_session(self, session_id: str, agent_id: str) -> Optional[Dict[str, Any]]:
		"""Get an agent session by session_id and agent_id."""
		response = self._make_request(
			"agent_sessions/get",
			{"session_id": session_id, "agent_id": agent_id},
			Dict[str, Any]
		)
		if not response.success:
			return None
		return response.data

	def update_agent_session(self, session_id: str, agent_id: str, status: str, fe_data: str = None) -> bool:
		"""Update an agent session's status."""
		response = self._make_request(
			"agent_sessions/update",
			{"session_id": session_id, "agent_id": agent_id, "status": status, "fe_data": fe_data},
			Dict[str, Any]
		)
		return response.success

	def create_agent_session(self, session_id: str, agent_id: str, started_at: str, status: str) -> bool:
		"""Create a new agent session."""
		response = self._make_request(
			"agent_sessions/create",
			{
				"session_id": session_id,
				"agent_id": agent_id,
				"started_at": started_at,
				"status": status
			},
			Dict[str, Any]
		)
		return response.success
