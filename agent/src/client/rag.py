import json
from pprint import pformat, pprint
import requests
from src.datatypes import StrategyData
from typing import List, TypedDict
import dataclasses


class RAGInsertData(TypedDict):
	strategy_id: str
	summarized_desc: str


class Metadata(TypedDict):
	created_at: str
	reference_id: str
	strategy_data: str  # JSON string containing StrategyData


class PageContent(TypedDict):
	metadata: Metadata
	page_content: str


class StrategyResponse(TypedDict):
	data: List[PageContent]
	msg: str
	status: str


class RAGClient:
	def __init__(
		self,
		agent_id: str,
		session_id: str,
		base_url: str = "https://supagent-rag-api.fly.dev",
	):
		self.base_url = base_url
		self.agent_id = agent_id
		self.session_id = session_id

	def save_result_batch(self, batch_data: List[StrategyData]) -> requests.Response:
		url = f"{self.base_url}/save_result_batch"

		payload = []

		for data in batch_data:
			payload.append(
				{
					"strategy": data.summarized_desc,
					"strategy_data": json.dumps(dataclasses.asdict(data)),
					"reference_id": data.strategy_id,
					"agent_id": self.agent_id,
					"session_id": self.session_id,
				}
			)

		response = requests.post(url, json=payload)
		response.raise_for_status()

		r = response.json()

		return r

	def relevant_strategy_raw(self, query: str) -> List[StrategyData]:
		url = f"{self.base_url}/relevant_strategy_raw"

		payload = {
			"query": query,
			"agent_id": self.agent_id,
			"session_id": self.session_id,
			"top_k": 1,
			"threshold": 0.5,
		}

		response = requests.post(url, json=payload)
		response.raise_for_status()

		r: StrategyResponse = response.json()
		pprint(r)

		strategy_datas = []
		for subdata in r["data"]:
			strategy_data: StrategyData = json.loads(
				subdata["metadata"]["strategy_data"]
			)
			strategy_datas.append(strategy_data)

		return strategy_datas
