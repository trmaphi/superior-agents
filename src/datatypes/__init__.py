from dataclasses import dataclass


@dataclass
class StrategyData:
	idx: int
	name: str
	inserted_at: str
	ran_at: str
	strategy_result: str
	reasoning: str
