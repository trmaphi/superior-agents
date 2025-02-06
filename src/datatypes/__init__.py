from dataclasses import dataclass


@dataclass
class StrategyData:
	name: str
	idx: int | None = None
	inserted_at: str | None = None
	ran_at: str | None = None
	strategy_result: str | None = None
	reasoning: str | None = None
