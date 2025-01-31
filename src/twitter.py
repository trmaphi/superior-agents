from abc import ABC, abstractmethod
from ast import Assert
from dataclasses import dataclass
from locale import textdomain
from pathlib import Path
import random
from typing import Any, List, TypeGuard
from venv import create

from loguru import logger
import tweepy
from result import Err, Ok, Result


@dataclass
class TweetData:
	id: str | None = None
	text: str | None = None
	created_at: str | None = None
	author_id: str | None = None
	author_username: str | None = None
	thread_id: str | None = None


def is_tweet_data_list(xs: List[Any]) -> TypeGuard[List[TweetData]]:
	return all(isinstance(x, TweetData) for x in xs)


@dataclass
class AccountData:
	id: str | None = None
	username: str | None = None
	followers_count: int | None = None


def is_account_data_list(xs: List[Any]) -> TypeGuard[List[AccountData]]:
	return all(isinstance(x, AccountData) for x in xs)


class TweepyTwitterClient:
	def __init__(self, client: tweepy.Client, api_client: tweepy.API):
		self.client = client
		self.api_client = api_client

	def reply_tweet(
		self,
		text: str,
		tweet_id: str,
	) -> Result[TweetData, str]:
		try:
			create_tweet_data = self.client.create_tweet(
				text=text, in_reply_to_tweet_id=tweet_id
			)
			assert isinstance(
				create_tweet_data, tweepy.Response
			), "Create tweet data is not a proper tweepy.Response"
			assert (
				create_tweet_data.data is not None
			), "Create tweet data doesnt have data"
		except AssertionError as e:
			logger.error(
				f"TweepyTwitterClient.reply_tweet: {e}, `create_tweet_data` is {create_tweet_data}"
			)
			return Err(
				f"TweepyTwitterClient.reply_tweet: {e}, `create_tweet_data` is {create_tweet_data}"
			)
		except Exception as e:
			logger.error(
				f"TweepyTwitterClient.reply_tweet: Tweepy create tweet failed: {e}"
			)
			return Err(
				f"TweepyTwitterClient.reply_tweet: Tweepy create tweet failed: {e}"
			)

		data = TweetData(
			id=create_tweet_data.data.id,
			text=create_tweet_data.data.text,
			created_at=str(create_tweet_data.data.created_at),
		)
		logger.info(data)

		return Ok(data)

	def post_tweet(
		self,
		text: str,
	) -> Result[TweetData, str]:
		try:
			create_tweet_data = self.client.create_tweet(
				text=text,
			)

			assert isinstance(
				create_tweet_data, tweepy.Response
			), "Create tweet data is not a proper tweepy.Response"
			assert (
				create_tweet_data.data is not None
			), "Create tweet data doesnt have data"
		except AssertionError as e:
			logger.error(
				f"TweepyTwitterClient.post_tweet: {e}, `create_tweet_data` is {create_tweet_data}"
			)
			return Err(
				f"TweepyTwitterClient.post_tweet: {e}, `create_tweet_data` is {create_tweet_data}"
			)
		except Exception as e:
			logger.error(
				f"TweepyTwitterClient.post_tweet: Tweepy create tweet failed: {e}"
			)
			return Err(
				f"TweepyTwitterClient.post_tweet: Tweepy create tweet failed: {e}"
			)

		data = TweetData(
			id=create_tweet_data.data["id"],
			text=create_tweet_data.data["text"],
			created_at=create_tweet_data.data["created_at"],
		)
		logger.info(data)

		return Ok(data)

	def quote_tweet(
		self,
		text: str,
		tweet_id: str,
	) -> Result[TweetData, str]:
		try:
			create_tweet_data = self.client.create_tweet(
				text=text,
				quote_tweet_id=tweet_id,
			)

			assert isinstance(
				create_tweet_data, tweepy.Response
			), "Create tweet data is not a proper tweepy.Response"
			assert (
				create_tweet_data.data is not None
			), "Create tweet data doesnt have data"
		except Exception as e:
			logger.error(
				f"TweepyTwitterClient.quote_tweet: Tweepy create tweet failed: {e}"
			)
			return Err(
				f"TweepyTwitterClient.quote_tweet: Tweepy create tweet failed: {e}"
			)

		if not isinstance(create_tweet_data, tweepy.Response):
			logger.error(
				"TweepyTwitterClient.quote_tweet: Create tweet data is not a proper tweepy.Response"
			)
			return Err(
				"TweepyTwitterClient.quote_tweet: Create tweet data is not a proper tweepy.Response"
			)

		if create_tweet_data.data is None:
			logger.error(
				"TweepyTwitterClient.quote_tweet: Create tweet data doesnt have data"
			)
			return Err(
				"TweepyTwitterClient.quote_tweet: Create tweet data doesnt have data"
			)

		data = TweetData(
			id=create_tweet_data.data.id,
			text=create_tweet_data.data.text,
			created_at=str(create_tweet_data.data.created_at),
		)
		logger.info(data)

		return Ok(data)

	def like_tweet(
		self,
		tweet_id: str,
	) -> Result[None, str]:
		try:
			like_tweet_data = self.client.like(tweet_id=tweet_id)

			assert isinstance(
				like_tweet_data, tweepy.Response
			), "Like tweet data is not a proper tweepy.Response"
		except AssertionError as e:
			logger.error(
				f"TweepyTwitterClient.like_tweet: {e}, `like_tweet_data` is {like_tweet_data}"
			)
			return Err(
				f"TweepyTwitterClient.like_tweet: {e}, `like_tweet_data` is {like_tweet_data}"
			)
		except Exception as e:
			logger.error(
				f"TweepyTwitterClient.like_tweet: Tweepy like tweet failed: {e}"
			)
			return Err(f"TweepyTwitterClient.like_tweet: Tweepy like tweet failed: {e}")

		return Ok(None)

	def retweet_tweet(self, tweet_id: str) -> Result[None, str]:
		try:
			retweet_tweet_data = self.client.retweet(tweet_id=tweet_id)

			assert isinstance(
				retweet_tweet_data, tweepy.Response
			), "Retweet tweet data is not a proper tweepy.Response"
		except AssertionError as e:
			logger.error(
				f"TweepyTwitterClient.retweet_tweet: {e}, `retweet_tweet_data` is {retweet_tweet_data}"
			)
			return Err(
				f"TweepyTwitterClient.retweet_tweet: {e}, `retweet_tweet_data` is {retweet_tweet_data}"
			)
		except Exception as e:
			logger.error(
				f"TweepyTwitterClient.retweet_tweet: Tweepy retweet tweet failed: {e}"
			)
			return Err(
				f"TweepyTwitterClient.retweet_tweet: Tweepy retweet tweet failed: {e}"
			)

		return Ok(None)

	def get_me_id(self) -> Result[str, str]:
		try:
			get_me_data = self.client.get_me()

			assert isinstance(
				get_me_data, tweepy.Response
			), "Get me data is not a proper tweepy.Response"
			assert isinstance(
				get_me_data.data, tweepy.User
			), "Get me subdata is not a tweepy user"
		except AssertionError as e:
			logger.error(
				f"TweepyTwitterClient.get_me_id: {e}, `get_me_data` is {get_me_data}"
			)
			return Err(
				f"TweepyTwitterClient.get_me_id: {e}, `get_me_data` is {get_me_data}"
			)
		except Exception as e:
			logger.error(f"TweepyTwitterClient.get_me_id: {e}")
			return Err(f"TweepyTwitterClient.get_me_id: {e}")

		log_data = {
			"me_id": str(get_me_data.data.id),
			"me_username": get_me_data.data.username,
		}
		logger.info(log_data)

		return Ok(str(get_me_data.data.id))

	def get_tweet(self, tweet_id: str) -> Result[TweetData, str]:
		try:
			get_tweet_data = self.client.get_tweet(tweet_id)

			assert isinstance(
				get_tweet_data, tweepy.Response
			), "Get tweet data is not a proper tweepy.Response"
			assert isinstance(
				get_tweet_data.data, tweepy.Tweet
			), "Get tweet subdata is not a tweepy tweet"
		except AssertionError as e:
			logger.error(
				f"TweepyTwitterClient.get_tweet: {e}, `get_tweet_data` is {get_tweet_data}"
			)
			return Err(
				f"TweepyTwitterClient.get_tweet: {e}, `get_tweet_data` is {get_tweet_data}"
			)
		except Exception as e:
			logger.error(f"TweepyTwitterClient.get_tweet: {e}")
			return Err(f"TweepyTwitterClient.get_tweet: {e}")

		tweet_data = TweetData(
			id=str(get_tweet_data.data.id),
			text=get_tweet_data.data.text,
			created_at=get_tweet_data.data.created_at.isoformat(),
		)
		log_data = {"tweet_data": tweet_data}
		logger.info(log_data)

		return Ok(tweet_data)

	def get_mentions_of_user(
		self, id: str, start_time: str
	) -> Result[List[TweetData], str]:
		try:
			response = self.client.get_users_mentions(
				id=id,
				expansions=["referenced_tweets.id"],
				tweet_fields=["created_at", "conversation_id", "author_id"],
				max_results=10,
			)

			assert isinstance(
				response, tweepy.Response
			), "Get users mentions data is not a tweepy response"
			assert isinstance(
				response.data, list
			), "Get users mentions subdata is not a list"
		except AssertionError as e:
			logger.error(
				f"TweepyTwitterClient.get_users_mentions: {e}, `response` is {response}"
			)
			return Err(
				f"TweepyTwitterClient.get_users_mentions: {e}, `response` is {response}"
			)
		except Exception as e:
			logger.error(f"TweepyTwitterClient.get_users_mentions: {e}")
			return Err(f"TweepyTwitterClient.get_users_mentions: {e}")

		tweet_datas = [
			TweetData(
				id=mention.id,
				text=mention.text,
				created_at=mention.created_at.isoformat(),
				author_id=mention.author_id,
				thread_id=mention.conversation_id,
			)
			for mention in response.data
		]

		log_data = {
			"id": id,
			"start_time": start_time,
			"mentions": tweet_datas,
		}
		logger.info(log_data)

		return Ok(tweet_datas)

	def sample_my_followers(
		self, max_results=100, sample=100
	) -> Result[List[AccountData], str]:
		# Get your own user ID
		get_me_id_result = self.get_me_id()

		if err := get_me_id_result.err():
			logger.error(
				f"TweepyTwitterClient.sample_my_followers, failed to get own user ID, err: \n{err}"
			)
			return Err(
				f"TweepyTwitterClient.sample_my_followers: Failed to get own user ID, err: \n{err}"
			)

		me_id = get_me_id_result.unwrap()

		# Fetch followers
		followers = []
		pagination_token = None

		while True:
			try:
				response = self.client.get_users_followers(
					id=me_id,
					max_results=100,  # Max per request (100 for standard tier)
					pagination_token=pagination_token,
					user_fields=["username", "name", "created_at"],
				)

				assert isinstance(
					response, tweepy.Response
				), "Get followers data is not a tweepy response"
				assert isinstance(
					response.data, list
				), "Get followers subdata is not a list"
			except AssertionError as e:
				logger.error(
					f"TweepyTwitterClient.sample_my_followers, `response` is {response}, err: \n{e}"
				)
				return Err(
					f"TweepyTwitterClient.sample_my_followers, `response` is {response}, err: \n{e}"
				)
			except Exception as e:
				logger.error(f"TweepyTwitterClient.get_users_followers, err: \n{e}")
				return Err(f"TweepyTwitterClient.get_users_followers, err: \n{e}")

			followers.extend(response.data)
			pagination_token = response.meta.get("next_token")

			if not pagination_token or len(followers) >= max_results:
				break

		data = [
			AccountData(
				id=str(f.id()),
				username=str(f.username),
				followers_count=int(f.public_metrics.followers_count),
			)
			for f in followers
		]
		data = random.sample(data, sample) if sample else data

		return Ok(data)

	def get_global_recent_tweets(
		self, query: str, max_results: int = 10
	) -> Result[List[TweetData], str]:
		try:
			response = self.client.search_recent_tweets(
				query=query,
				max_results=max_results,
				tweet_fields=["created_at", "author_id"],
			)
			assert isinstance(
				response, tweepy.Response
			), "Response is not a tweepy.Response"
			assert isinstance(response.data, list), "Response data is not a list"
		except AssertionError as e:
			logger.error(
				f"TweepyTwitterClient.get_global_recent_tweets: {e}, response is {response}"
			)
			return Err(
				f"TweepyTwitterClient.get_global_recent_tweets: {e}, response is {response}"
			)
		except Exception as e:
			logger.error(f"TweepyTwitterClient.get_global_recent_tweets: {e}")
			return Err(f"TweepyTwitterClient.get_global_recent_tweets: {e}")

		tweets = [
			TweetData(id=str(tweet.id), text=tweet.text, created_at=tweet.created)
			for tweet in response.data
		]
		logger.info(f"Retrieved {len(tweets)} global recent tweets")
		return Ok(tweets)

	def get_count_of_followers(self) -> Result[int, str]:
		try:
			response = self.client.get_me(user_fields=["public_metrics"])
			assert isinstance(
				response, tweepy.Response
			), "Get me data is not a proper tweepy.Response"
			assert isinstance(
				response.data, tweepy.User
			), "Get me subdata is not a tweepy user"
			followers_count = response.data.public_metrics["followers_count"]
		except AssertionError as e:
			logger.error(
				f"TweepyTwitterClient.get_followers_counts: {e}, response is {response}"
			)
			return Err(
				f"TweepyTwitterClient.get_followers_counts: {e}, response is {response}"
			)
		except Exception as e:
			logger.error(f"TweepyTwitterClient.get_followers_counts: {e}")
			return Err(f"TweepyTwitterClient.get_followers_counts: {e}")

		logger.info(f"Followers count: {followers_count}")
		return Ok(followers_count)

	def get_recent_tweets_of_followers(
		self, max_per_user: int = 5
	) -> Result[List[TweetData], str]:
		followers_result = self.sample_my_followers()

		if err := followers_result.err():
			logger.error(
				f"TweepyTwitterClient.get_recent_tweets_of_followers, failed to get list of followers, err: \n{err}"
			)
			return Err(
				f"TweepyTwitterClient.get_recent_tweets_of_followers, failed to get list of followers, err: \n{err}"
			)

		followers = followers_result.unwrap()
		all_tweets = []
		errors = []

		for follower in followers:
			try:
				response = self.client.get_users_tweets(
					id=follower.id,
					max_results=max_per_user,
					tweet_fields=["created_at"],
				)
				assert isinstance(
					response, tweepy.Response
				), "Response is not a tweepy.Response"
				assert response.data is not None
			except AssertionError as e:
				logger.error(f"Error fetching tweets for follower {follower.id}: {e}")
				errors.append(f"Error fetching tweets for follower {follower.id}: {e}")
				continue
			except Exception as e:
				errors.append(f"Error fetching tweets for follower {follower.id}: {e}")
				logger.error(f"Error fetching tweets for follower {follower.id}: {e}")
				continue

			follower_tweets = [
				TweetData(
					id=str(tweet.id), text=tweet.text, created_at=tweet.created_at
				)
				for tweet in response.data
			]
			all_tweets.extend(follower_tweets)

		if len(all_tweets) == 0 and len(errors) > 0:
			formatted_err = "\n".join(errors)
			return Err(
				f"Errors occurred while fetching tweets for followers: {formatted_err}"
			)

		return Ok(all_tweets)

	def get_tweet_retweeters(
		self, tweet_id: str, count=100
	) -> Result[List[AccountData], str]:
		try:
			response = self.client.get_retweeters(tweet_id, max_results=count)

			assert isinstance(
				response, tweepy.Response
			), "Response is not a tweepy.Response"
			assert isinstance(response.data, list), "Response data is not a list"
			assert is_account_data_list(
				response.data
			), "Response data is not a list of tweepy.User"
		except AssertionError as e:
			logger.error(
				f"TweepyTwitterClient.get_tweet_retweeters: {e}, response is {response}"
			)
			return Err(
				f"TweepyTwitterClient.get_tweet_retweeters: {e}, response is {response}"
			)
		except Exception as e:
			logger.error(f"TweepyTwitterClient.get_tweet_retweeters: {e}")
			return Err(f"TweepyTwitterClient.get_tweet_retweeters: {e}")

		response.data

		data = [
			AccountData(
				id=str(user.id),
				followers_count=user.followers_count,
				username=user.username,
			)
			for user in response.data
		]
		logger.info(f"Retrieved {len(data)} retweeters for tweet {tweet_id}")

		return Ok(data)
