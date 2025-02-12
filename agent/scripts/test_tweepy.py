from ast import Tuple
from datetime import datetime
from pydantic import BaseModel
import requests
import tweepy
from typing import List
from src.secret import get_secrets_from_vault
from loguru import logger
import random
import os


get_secrets_from_vault()

API_KEY = os.getenv("API_KEY") or ""
API_SECRET = os.getenv("API_KEY_SECRET") or ""
BEARER_TOKEN = os.getenv("BEARER_TOKEN") or ""
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN") or ""
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET") or ""

logger.info(f"API_KEY: {API_KEY[:5]}...{API_KEY[-5:]}")
logger.info(f"API_SECRET: {API_SECRET[:5]}...{API_SECRET[-5:]}")
logger.info(f"BEARER_TOKEN: {BEARER_TOKEN[:5]}...{BEARER_TOKEN[-5:]}")
logger.info(f"ACCESS_TOKEN: {ACCESS_TOKEN[:5]}...{ACCESS_TOKEN[-5:]}")
logger.info(
	f"ACCESS_TOKEN_SECRET: {ACCESS_TOKEN_SECRET[:5]}...{ACCESS_TOKEN_SECRET[-5:]}"
)


def sample_followers(
	client: tweepy.Client, user_id: str, max_results: int = 100, sample_size: int = 100
) -> List[dict]:
	"""
	Get a sample of followers for a given user ID

	Args:
		client: Authenticated tweepy client
		user_id: Twitter user ID to fetch followers for
		max_results: Maximum number of followers to fetch in total
		sample_size: Number of random followers to return from the results

	Returns:
		List of dictionaries containing follower information with keys:
		- id: str
		- username: str
		- followers_count: int

	Raises:
		RuntimeError: If unable to fetch followers
	"""
	followers = []
	pagination_token = None

	while True:
		try:
			response = client.get_users_followers(
				id=user_id,
				max_results=100,  # Max per request (100 for standard tier)
				pagination_token=pagination_token,
				user_fields=["username", "name", "created_at", "public_metrics"],
			)

			assert isinstance(
				response, tweepy.Response
			), "Get followers data is not a tweepy response"
			assert isinstance(
				response.data, list
			), "Get followers subdata is not a list"

			# Convert tweepy objects to primitive dictionaries
			followers.extend(
				[
					{
						"id": str(f.id),
						"username": str(f.username),
						"followers_count": int(f.public_metrics["followers_count"]),
					}
					for f in response.data
				]
			)

			pagination_token = response.meta.get("next_token")

			if not pagination_token or len(followers) >= max_results:
				break

		except (AssertionError, Exception) as e:
			error_msg = f"Failed to fetch followers: {str(e)}"
			logger.error(error_msg)
			raise RuntimeError(error_msg)

	# Sample the results if requested
	if sample_size and len(followers) > sample_size:
		followers = random.sample(followers, sample_size)

	return followers


def get_recent_tweets_of_followers(
	client: tweepy.Client, follower_ids: List[str], max_per_user: int = 5
) -> List[Tuple]:
	"""
	Get recent tweets from a list of followers

	Args:
		client: Authenticated tweepy client
		follower_ids: List of follower IDs to fetch tweets from
		max_per_user: Maximum number of tweets to fetch per user

	Returns:
		List of TweetData objects containing tweet information

	Raises:
		RuntimeError: If unable to fetch tweets or if no tweets were retrieved
	"""
	all_tweets = []
	errors = []

	for follower_id in follower_ids:
		try:
			response = client.get_users_tweets(
				id=follower_id,
				max_results=max_per_user,
				tweet_fields=["created_at"],
			)
			assert isinstance(
				response, tweepy.Response
			), "Response is not a tweepy.Response"
			assert response.data is not None

			follower_tweets = [
				(str(tweet.id), tweet.text, tweet.created_at) for tweet in response.data
			]
			all_tweets.extend(follower_tweets)

		except (AssertionError, Exception) as e:
			error_msg = f"Error fetching tweets for follower {follower_id}: {e}"
			logger.error(error_msg)
			errors.append(error_msg)
			continue

	if len(all_tweets) == 0 and len(errors) > 0:
		formatted_err = "\n".join(errors)
		raise RuntimeError(
			f"Errors occurred while fetching tweets for followers: {formatted_err}"
		)

	return all_tweets


class Tweet(BaseModel):
	author_id: str
	created_at: datetime
	id: str
	text: str
	username: str


def get_user_timeline(user_id: str, bearer_token: str) -> List[Tweet]:
	url = f"https://api.x.com/2/users/{user_id}/timelines/reverse_chronological"
	headers = {"Authorization": f"Bearer {bearer_token}"}

	response = requests.get(url, headers=headers).json()
	print(response)
	return [Tweet(**tweet) for tweet in response["data"]]


# Example usage:
# tweets = get_user_timeline("2244994945", "your_bearer_token")
# for tweet in tweets:
#     print(f"{tweet.username}: {tweet.text}")
if __name__ == "__main__":
	user_id = "1850116704090931200"
	client = tweepy.Client(
		bearer_token=BEARER_TOKEN,
		consumer_key=API_KEY,
		consumer_secret=API_SECRET,
		access_token=ACCESS_TOKEN,
		access_token_secret=ACCESS_TOKEN_SECRET,
	)

	# followers = sample_followers(client, user_id=user_id)
	# id_of_followers = [follower["id"] for follower in followers]
	# tweets = get_recent_tweets_of_followers(client, id_of_followers)
	tweets = get_user_timeline(user_id, BEARER_TOKEN)
	for tweet in tweets:
		print(f"{tweet.username}: {tweet.text}")

	# for tweet in tweets:
	# 	print(tweet)
