from contextlib import contextmanager
from datetime import datetime
import random
import sqlite3
from abc import ABC, abstractmethod
from typing import List, TypeAlias

from loguru import logger

from src.types import ChatHistory, Message, StrategyData


class DB(ABC):
	@abstractmethod
	def __init__(self, *args, **kwargs):
		pass

	@abstractmethod
	def sample_all_strategies(self, count=20) -> List[StrategyData]:
		pass

	@abstractmethod
	def get_latest_non_tried_strategy(self) -> StrategyData | None:
		pass

	@abstractmethod
	def get_latest_tried_strategy(self) -> StrategyData | None:
		pass

	@abstractmethod
	def insert_strategies(self, strategies: List[str]):
		pass

	@abstractmethod
	def insert_chat_history(self, chat_history: ChatHistory):
		pass


class SqliteDB(DB):
	def __init__(self, db_path="db/agentic_yaitsiu.db"):
		self.db_name = db_path
		self.init_database()

	def init_database(self) -> None:
		"""Initialize the SQLite database and create tables if they don't exist"""
		try:
			with sqlite3.connect(self.db_name) as conn:
				cursor = conn.cursor()
				cursor.execute("""
					CREATE TABLE IF NOT EXISTS chat_history (
						id INTEGER PRIMARY KEY AUTOINCREMENT,
						role TEXT NOT NULL,
						content TEXT NOT NULL,
						metadata TEXT
					)
				""")
				cursor.execute("""
					CREATE TABLE IF NOT EXISTS strategy_data (
						id INTEGER PRIMARY KEY AUTOINCREMENT,
						name TEXT NOT NULL,
						inserted_at TEXT NOT NULL,
						ran_at TEXT,
						strategy_result TEXT,
						reasoning TEXT 
					)
				""")
				conn.commit()

			return None
		except Exception as e:
			logger.error(
				f"DatabaseManager.init_database: Database initialization error: {e}"
			)
			raise e

	@contextmanager
	def get_conn(self):
		with sqlite3.connect(self.db_name) as conn:
			yield conn

	def sample_all_strategies(self, count=5) -> List[StrategyData]:
		try:
			with self.get_conn() as conn:
				cursor = conn.cursor()
				cursor.execute(
					"""
					SELECT 
						id, 
						name, 
						inserted_at,
						ran_at, 
						strategy_result, 
						reasoning
					FROM strategy_data 
					ORDER BY id
					"""
				)

				strategies = cursor.fetchall()
				strategies = [
					StrategyData(
						idx=strategy["id"],
						name=strategy["name"],
						inserted_at=strategy["inserted_at"],
						ran_at=strategy["ran_at"],
						strategy_result=strategy["strategy_result"],
						reasoning=strategy["reasoning"],
					)
					for strategy in strategies
				]

				if len(strategies) < count:
					return strategies
				else:
					return random.sample(strategies, count)
		except Exception as e:
			logger.error(
				f"DatabaseManager.sample_all_strategies: Error sampling strategies: {e}"
			)
			raise e

	def get_latest_non_tried_strategy(self) -> StrategyData | None:
		try:
			with self.get_conn() as conn:
				cursor = conn.cursor()
				cursor.execute(
					"""
					SELECT 
						id, 
						name, 
						inserted_at,
						ran_at, 
						strategy_result, 
						reasoning
					FROM strategy_data 
					WHERE strategy_result IS NULL 
					ORDER BY id DESC LIMIT 1
					"""
				)
				strategy = cursor.fetchone()

				if strategy is None:
					logger.info(
						"DatabaseManager.get_latest_non_tried_strategy: No non-tried strategy found."
					)
					return None

				id, name, inserted_at, ran_at, strategy_result, reasoning = strategy

				return StrategyData(
					idx=id,
					name=name,
					inserted_at=inserted_at,
					ran_at=ran_at,
					strategy_result=strategy_result,
					reasoning=reasoning,
				)
		except Exception as e:
			logger.error(
				f"DatabaseManager.sample_all_strategies: Error sampling strategies: {e}"
			)
			raise e

	def get_latest_tried_strategy(self) -> StrategyData | None:
		try:
			with self.get_conn() as conn:
				cursor = conn.cursor()
				cursor.execute(
					"""
					SELECT 
						id,
						strategy,
						inserted_at,
						ran_at,
						strategy_result,
						reasoning
					FROM strategy_data 
					WHERE strategy_result IS NOT NULL  
					ORDER BY ran_at DESC               
					LIMIT 1                           
					"""
				)

				strategy = cursor.fetchone()

				if strategy is None:
					logger.info(
						"DatabaseManager.get_latest_non_tried_strategy: Strategy is found at all."
					)
					return None

				return StrategyData(
					idx=strategy["id"],
					name=strategy["name"],
					inserted_at=strategy["inserted_at"],
					ran_at=strategy["ran_at"],
					strategy_result=strategy["strategy_result"],
					reasoning=strategy["reasoning"],
				)
		except Exception as e:
			logger.error(
				f"DatabaseManager.sample_all_strategies: Error sampling strategies: {e}"
			)
			raise e

	def insert_strategies(self, strategies: List[str]):
		try:
			now = datetime.now().isoformat()
			with self.get_conn() as conn:
				cursor = conn.cursor()
				for strategy in strategies:
					cursor.execute(
						"""
						INSERT INTO strategy_data (name, inserted_at) 
						VALUES (?, ?)
						""",
						(strategy, now),
					)
				conn.commit()

				return None
		except Exception as e:
			logger.error(
				f"DatabaseManager.insert_strategies: Error inserting strategies: {e}"
			)
			raise e

	def insert_chat_history(self, chat_history: ChatHistory):
		try:
			with self.get_conn() as conn:
				cursor = conn.cursor()
				for message in chat_history.messages:
					cursor.execute(
						"""
						INSERT INTO chat_history (role, content, metadata) 
						VALUES (?, ?, ?)
						""",
						(message.role, message.content, str(message.metadata)),
					)
				conn.commit()

				return None
		except Exception as e:
			logger.error(
				f"DatabaseManager.insert_chat_history: Error inserting chat history: {e}"
			)
			raise e

	def get_all_chat_history(self) -> List[Message]:
		try:
			with self.get_conn() as conn:
				cursor = conn.cursor()
				cursor.execute(
					"""
					SELECT *
					FROM chat_history
					ORDER BY id
					""",
				)
				messages = cursor.fetchall()
				messages = [
					Message(
						role=role,
						content=content,
						metadata=metadata,
					)
					for idx, role, content, metadata in messages
				]

				return messages
		except Exception as e:
			logger.error(
				f"DatabaseManager.get_all_chat_history: Error getting: {e}"
			)
			raise e
