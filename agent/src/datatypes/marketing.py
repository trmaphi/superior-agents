from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum




@dataclass
class NewsData:
	date: datetime
	title: str
	body: str
	url: str
	source: str
	image: Optional[str] = None

	@staticmethod
	def from_dict(data: dict) -> "NewsData":
		"""Create a NewsArticle instance from a dictionary."""
		# Convert ISO format string to datetime
		date = datetime.fromisoformat(data["date"].replace("Z", "+00:00"))

		return NewsData(
			date=date,
			title=data["title"],
			body=data["body"],
			url=data["url"],
			image=data.get("image"),  # Using get() in case image is missing
			source=data["source"],
		)

	def to_dict(self) -> dict:
		"""Convert the NewsArticle instance to a dictionary."""
		return {
			"date": self.date.isoformat(),
			"title": self.title,
			"body": self.body,
			"url": self.url,
			"image": self.image,
			"source": self.source,
		}


class MarketingAgentState(Enum):
	# Failed states
	FAILED_GENERATION = "failed_generation"  # Failed at code generation
	FAILED_EXECUTION = "failed_execution"  # Failed at code execution
	FAILED_MAX_RETRIES = "failed_max_retries"  # Failed after max retries

	# Success states
	SUCCESS_WITH_OUTPUT = "success_with_output"  # Succeeded with good output
	SUCCESS_NEEDS_IMPROVEMENT = (
		"success_needs_improvement"  # Succeeded but could be better
	)

	@property
	def is_success(self) -> bool:
		return self.name.startswith("SUCCESS")

	@property
	def is_failure(self) -> bool:
		return self.name.startswith("FAILED")
