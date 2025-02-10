from dataclasses import dataclass
from typing import Dict, Any, Optional, List, TypeVar, cast, Generic
import requests
import json
from enum import Enum
from datetime import datetime

from src.datatypes import StrategyData

T = TypeVar('T')

class ApiError(Exception):
	pass

class StrategyStatus(Enum):
	ACTIVE = "active"
	INACTIVE = "inactive"
	TESTING = "testing"

@dataclass
class Strategy:
	id: str
	agent_id: str
	summarized_desc: str
	full_desc: str
	parameters: Dict[str, Any]
	created_at: datetime
	updated_at: datetime
	status: StrategyStatus

@dataclass
class StrategyInsertData:
	summarized_desc: str
	full_desc: str
	parameters: Dict[str, Any]

@dataclass
class ApiResponse(Generic[T]):
	success: bool
	data: Optional[T]
	error: Optional[str]

class TradingDBAPI:
	def __init__(self, base_url: str = "http://localhost:9020/api_v1", api_key: str = "ccm2q324t1qv1eulq894"):
		self.base_url = base_url
		self.headers = {
			"x-api-key": api_key,
			"Content-Type": "application/json"
		}
	
	def _make_request(self, endpoint: str, data: Dict[str, Any], response_type: type[T]) -> ApiResponse[T]:
		try:
			response = requests.post(
				f"{self.base_url}/{endpoint}",
				headers=self.headers,
				json=data
			)
			response.raise_for_status()
			return ApiResponse(success=True, data=cast(T, response.json()), error=None)
		except requests.exceptions.RequestException as e:
			return ApiResponse(success=False, data=None, error=str(e))

	def fetch_params_using_agent_id(self, agent_id: str) -> Dict[str, Dict[str, Any]]:
		agent_response = self._make_request("agent/get", {"id": agent_id}, Dict[str, Any])
		if not agent_response.success:
			raise ApiError(f"Failed to verify agent: {agent_response.error}")
			
		strategies_response = self._make_request("strategies/get", {}, List[Dict[str, Any]])
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
					"full_desc": str(strategy["full_desc"])
				}
			except (KeyError, json.JSONDecodeError, ValueError) as e:
				raise ApiError(f"Error processing strategy {strategy.get('id')}: {str(e)}")
				
		return params

	def insert_strategy_and_result(self, agent_id: str, strategy_result: StrategyInsertData) -> bool:
		agent_response = self._make_request("agent/get", {"id": agent_id}, Dict[str, Any])
		if not agent_response.success:
			raise ApiError(f"Failed to verify agent: {agent_response.error}")
			
		strategy_data = {
			"agent_id": agent_id,
			"summarized_desc": strategy_result.summarized_desc,
			"full_desc": strategy_result.full_desc,
			"parameters": json.dumps(strategy_result.parameters)
		}
		
		response = self._make_request("strategies/create", strategy_data, Dict[str, Any])
		if not response.success:
			raise ApiError(f"Failed to insert strategy: {response.error}")
			
		return True

	def fetch_latest_strategy(self, agent_id: str) -> Optional[StrategyData]:
		strategies_response = self._make_request("strategies/get", {}, List[Dict[str, Any]])
		if not strategies_response.success:
			raise ApiError(f"Failed to fetch strategies: {strategies_response.error}")
			
		strategies = strategies_response.data or []
		agent_strategies = [
			s for s in strategies 
			if s.get("agent_id") == agent_id
		]
		
		if not agent_strategies:
			return None
			
		latest = max(agent_strategies, key=lambda s: s.get("created_at", ""))
		
		return StrategyData(
			id=str(latest["id"]),
			agent_id=agent_id,
			parameters=json.loads(latest["parameters"]),
			summarized_desc=str(latest["summarized_desc"]),
			strategy_result=latest["strategy_result"],
			full_desc=str(latest["full_desc"]),
			created_at=latest["created_at"],
			updated_at=latest["updated_at"]
		)

